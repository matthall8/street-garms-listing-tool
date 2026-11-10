"""The FastAPI routes: uploads in, status codes and pages out.

Every test here runs offline. Two guards keep it that way:

- `client` stops create_app() loading .env, rather than deleting the API key
  afterwards. monkeypatch restores whatever it deletes when a test ends, so
  deleting a key that .env just loaded would hand it to every later test.
- `no_real_extraction` makes any test that reaches the pipeline unpatched fail
  by name. It uses pytest.fail because the route's `except Exception` would
  swallow an ordinary exception into a normal-looking 502.

The patch target is app.routes.extract_bytes, NOT labels.pipeline.extract_bytes
— routes.py does `from labels.pipeline import extract_bytes`, which binds the
name at import time, so patching the source module would have no effect.
"""

import inspect
import io
import os

import pytest
from fastapi import FastAPI, UploadFile
from fastapi.routing import APIRoute, iter_route_contexts
from fastapi.testclient import TestClient

from app import create_app, routes
from labels.schemas import Extraction


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr("dotenv.load_dotenv", lambda *args, **kwargs: False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    app = create_app()
    leaked = "ANTHROPIC_API_KEY" in os.environ
    assert not leaked, "create_app() loaded .env despite the patch"
    return TestClient(app)


@pytest.fixture(autouse=True)
def no_real_extraction(monkeypatch):
    def unpatched(art, source=""):
        pytest.fail("extract_bytes was not patched: this test would call the API")

    monkeypatch.setattr(routes, "extract_bytes", unpatched)


@pytest.fixture
def extract_calls(monkeypatch):
    """Patch the pipeline with a fake that succeeds and records each call."""
    calls = []

    def fake_extract(art, source=""):
        calls.append({"art": art, "source": source})
        return _extraction(source)

    monkeypatch.setattr(routes, "extract_bytes", fake_extract)
    return calls


def failing_extract(art, source=""):
    raise TimeoutError("boom")


def _extraction(source: str) -> Extraction:
    return Extraction(
        source_image=source,
        art_number_raw="TESTCODE",
        art_base="TESTCODE",
        decoded="test decode",
        product_name="Test Jacket",
        year=None,
        season=None,
        brand=None,
        garment=None,
        legibility="clear",
        all_reads=[],
        flags=[],
        catalogue_match="miss",
        matched_art=None,
        needs_review=False,
    )


def _upload(filename: str, media_type: str) -> dict:
    return {"art_photo": (filename, io.BytesIO(b"x"), media_type)}


def test_no_photo_is_a_400(client):
    response = client.post("/")
    assert response.status_code == 400
    assert b"Add a photo of the label" in response.content


def test_unsupported_file_type_is_a_400(client):
    files = _upload("a.gif", "image/gif")
    response = client.post("/", files=files)
    assert response.status_code == 400
    assert b"Unsupported image" in response.content


@pytest.mark.parametrize("media_type", ["image/heic", "image/heif"])
def test_heic_and_heif_are_rejected(client, extract_calls, media_type):
    """The API doesn't take HEIC, so the form refuses it before any call."""
    files = _upload("label." + media_type.split("/")[1], media_type)
    response = client.post("/", files=files)
    assert response.status_code == 400
    assert b"Unsupported image" in response.content
    assert extract_calls == []


def test_failed_extraction_is_a_502(client, monkeypatch):
    monkeypatch.setattr(routes, "extract_bytes", failing_extract)
    files = _upload("a.png", "image/png")
    response = client.post("/", files=files)
    assert response.status_code == 502
    assert b"Extraction failed" in response.content
    assert b"boom" in response.content


@pytest.mark.parametrize("media_type", sorted(routes.ACCEPTED))
def test_supported_type_reaches_the_pipeline(client, extract_calls, media_type):
    filename = "label." + media_type.split("/")[1]
    files = _upload(filename, media_type)
    response = client.post("/", files=files)
    assert response.status_code == 200
    assert extract_calls == [
        {"art": (b"x", media_type), "source": filename}
    ]
    assert b"Test Jacket" in response.content


def test_a_stray_second_photo_is_ignored(client, extract_calls):
    """The form has one upload box; a details_photo field from an old form or
    a script never reaches the pipeline."""
    files = _upload("a.png", "image/png")
    files["details_photo"] = ("b.png", io.BytesIO(b"y"), "image/png")
    response = client.post("/", files=files)
    assert response.status_code == 200
    assert extract_calls == [{"art": (b"x", "image/png"), "source": "a.png"}]


def test_a_second_photo_alone_is_a_400(client, extract_calls):
    files = {"details_photo": ("b.png", io.BytesIO(b"y"), "image/png")}
    response = client.post("/", files=files)
    assert response.status_code == 400
    assert b"Add a photo of the label" in response.content
    assert extract_calls == []


def test_empty_file_field_is_a_400(client, extract_calls):
    """A browser sends the field with an empty filename when no file is chosen.
    Built by hand because httpx leaves out an empty filename."""
    body = (
        b"--b\r\n"
        b'Content-Disposition: form-data; name="art_photo"; filename=""\r\n'
        b"Content-Type: application/octet-stream\r\n\r\n"
        b"\r\n--b--\r\n"
    )
    response = client.post(
        "/", content=body, headers={"Content-Type": "multipart/form-data; boundary=b"}
    )
    assert response.status_code == 400
    assert b"Add a photo of the label" in response.content
    assert extract_calls == []


def test_parameters_on_the_content_type_are_ignored(client, extract_calls):
    response = client.post("/", files=_upload("label.jpg", "image/jpeg; charset=binary"))
    assert response.status_code == 200
    assert extract_calls == [{"art": (b"x", "image/jpeg"), "source": "label.jpg"}]


CAP = 16 * 1024 * 1024


def _upload_of(size: int) -> dict:
    return {"art_photo": ("a.png", io.BytesIO(b"x" * size), "image/png")}


def test_upload_at_the_cap_reaches_the_pipeline(client, extract_calls):
    response = client.post("/", files=_upload_of(CAP))
    assert response.status_code == 200
    assert len(extract_calls) == 1
    assert len(extract_calls[0]["art"][0]) == CAP


def test_upload_over_the_cap_is_a_413(client, extract_calls):
    response = client.post("/", files=_upload_of(CAP + 1))
    assert response.status_code == 413
    assert b"too large" in response.content
    assert extract_calls == []


def test_upload_of_unknown_size_counts_as_too_large():
    assert routes._too_large(UploadFile(io.BytesIO(b"x"), filename="a.png", size=None))


def test_no_route_handler_is_a_coroutine_function(client):
    """ADR-0008, D4: the read uses run_sync, which can't run in an `async def`
    route. APIRoutes only: FastAPI's own /docs and /openapi.json handlers are
    async. iter_route_contexts because app.routes hides an included router's
    routes, and a loop over it would find nothing and pass."""
    app = client.app
    assert isinstance(app, FastAPI)
    handlers = [
        c.original_route
        for c in iter_route_contexts(app.routes)
        if isinstance(c.original_route, APIRoute)
    ]
    assert handlers, "found no routes, so this test checked nothing"
    async_paths = [h.path for h in handlers if inspect.iscoroutinefunction(h.endpoint)]
    assert async_paths == []
