"""The Flask routes: uploads in, status codes and pages out.

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

import io
import os

import pytest

from app import create_app, routes
from labels.schemas import Extraction


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr("dotenv.load_dotenv", lambda *args, **kwargs: False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    app = create_app()
    leaked = "ANTHROPIC_API_KEY" in os.environ
    assert not leaked, "create_app() loaded .env despite the patch"
    app.config["TESTING"] = True
    return app.test_client()


@pytest.fixture(autouse=True)
def no_real_extraction(monkeypatch):
    def unpatched(art=None, details=None, source=""):
        pytest.fail("extract_bytes was not patched: this test would call the API")

    monkeypatch.setattr(routes, "extract_bytes", unpatched)


@pytest.fixture
def extract_calls(monkeypatch):
    """Patch the pipeline with a fake that succeeds and records each call."""
    calls = []

    def fake_extract(art=None, details=None, source=""):
        calls.append({"art": art, "details": details, "source": source})
        return _extraction(source)

    monkeypatch.setattr(routes, "extract_bytes", fake_extract)
    return calls


def failing_extract(art=None, details=None, source=""):
    raise TimeoutError("boom")


def _extraction(source: str) -> Extraction:
    return Extraction(
        source_image=source,
        art_number_raw="TESTCODE",
        decoded="test decode",
        product_name="Test Jacket",
        year=None,
        season=None,
        brand=None,
        garment=None,
        size=None,
        composition=None,
        made_in=None,
        certilogo=None,
        colour_observed=None,
        legibility="clear",
        all_reads=[],
        flags=[],
        catalogue_match="miss",
        matched_art=None,
        needs_review=False,
    )


def _upload(filename: str, media_type: str) -> dict:
    return {"art_photo": (io.BytesIO(b"x"), filename, media_type)}


def test_no_photo_is_a_400(client):
    response = client.post("/")
    assert response.status_code == 400
    assert b"Add a photo of the label" in response.data


def test_unsupported_file_type_is_a_400(client):
    data = _upload("a.gif", "image/gif")
    response = client.post("/", data=data, content_type="multipart/form-data")
    assert response.status_code == 400
    assert b"Unsupported image" in response.data


def test_failed_extraction_is_a_502(client, monkeypatch):
    monkeypatch.setattr(routes, "extract_bytes", failing_extract)
    data = _upload("a.png", "image/png")
    response = client.post("/", data=data, content_type="multipart/form-data")
    assert response.status_code == 502
    assert b"Extraction failed" in response.data
    assert b"boom" in response.data


@pytest.mark.parametrize("media_type", sorted(routes.ACCEPTED))
def test_supported_type_reaches_the_pipeline(client, extract_calls, media_type):
    filename = "label." + media_type.split("/")[1]
    data = _upload(filename, media_type)
    response = client.post("/", data=data, content_type="multipart/form-data")
    assert response.status_code == 200
    assert extract_calls == [
        {"art": (b"x", media_type), "details": None, "source": filename}
    ]
    assert b"Test Jacket" in response.data


def test_a_stray_second_photo_is_ignored(client, extract_calls):
    """The form has one upload box; a details_photo field from an old form or
    a script never reaches the pipeline."""
    data = _upload("a.png", "image/png")
    data["details_photo"] = (io.BytesIO(b"y"), "b.png", "image/png")
    response = client.post("/", data=data, content_type="multipart/form-data")
    assert response.status_code == 200
    assert extract_calls == [{"art": (b"x", "image/png"), "details": None, "source": "a.png"}]


def test_a_second_photo_alone_is_a_400(client, extract_calls):
    data = {"details_photo": (io.BytesIO(b"y"), "b.png", "image/png")}
    response = client.post("/", data=data, content_type="multipart/form-data")
    assert response.status_code == 400
    assert extract_calls == []
