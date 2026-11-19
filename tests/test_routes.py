"""The FastAPI routes: uploads in, status codes and pages out.

Every test here runs offline. Two guards keep it that way:

- `client` stops create_app() loading .env, rather than deleting the API key
  afterwards. monkeypatch restores whatever it deletes when a test ends, so
  deleting a key that .env just loaded would hand it to every later test.
- `no_real_extraction` makes any test that reaches the pipeline unpatched fail
  by name. It uses pytest.fail because the route's `except Exception` would
  swallow an ordinary exception into a normal-looking 502.
- `no_real_stores` does the same for POST /items' photo store and database.

The patch target is app.routes.extract_bytes, NOT labels.pipeline.extract_bytes
— routes.py does `from labels.pipeline import extract_bytes`, which binds the
name at import time, so patching the source module would have no effect.
"""

import inspect
import io
import logging
import os
from contextlib import contextmanager

import pytest
from fastapi import FastAPI, UploadFile
from fastapi.routing import APIRoute, iter_route_contexts
from fastapi.testclient import TestClient

from app import create_app, routes
from labels.pipeline import from_reading
from labels.schemas import AmbiguousCharacter, ArtNumberReading, Extraction
from tests import synthetic as s


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


# POST /items. The photo store and the database are faked through the names
# routes.py looks up at call time (photos.store_photo, db.connect,
# db.insert_item, db.confirm_item). `no_real_stores` fails any test that
# reaches them unpatched, with pytest.fail for the same reason as
# `no_real_extraction`.

PHOTO = b"\xff\xd8 invented upload bytes"


@pytest.fixture(autouse=True)
def no_real_stores(monkeypatch):
    def unpatched(*args, **kwargs):
        pytest.fail("a photo store or database call was not patched")

    monkeypatch.setattr(routes.photos, "store_photo", unpatched)
    monkeypatch.setattr(routes.db, "connect", unpatched)
    monkeypatch.setattr(routes.db, "insert_item", unpatched)
    monkeypatch.setattr(routes.db, "confirm_item", unpatched)


@pytest.fixture
def stored(monkeypatch):
    """Fake photo store and database that succeed and record each call."""
    calls = {"photo": [], "connect": 0, "insert": []}

    def store_photo(item_id, data, media_type):
        calls["photo"].append((item_id, data, media_type))

    @contextmanager
    def connect():
        calls["connect"] += 1
        yield "a connection"

    def insert_item(conn, **row):
        assert conn == "a connection"
        calls["insert"].append(row)

    monkeypatch.setattr(routes.photos, "store_photo", store_photo)
    monkeypatch.setattr(routes.db, "connect", connect)
    monkeypatch.setattr(routes.db, "insert_item", insert_item)
    return calls


def _photo(media_type: str = "image/jpeg") -> dict:
    return {"art_photo": ("label.jpg", io.BytesIO(PHOTO), media_type)}


def test_items_returns_only_the_id_and_the_value_shown(client, extract_calls, stored):
    response = client.post("/items", files=_photo())
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"id", "value_shown"}  # ADR-0008, D3, D4
    assert body["value_shown"] == "TESTCODE"

    (item_id, _, _), = stored["photo"]
    (row,) = stored["insert"]
    assert body["id"] == str(item_id) == str(row["item_id"])
    assert extract_calls[0]["source"] == str(item_id)  # never the filename


def test_items_one_id_per_upload(client, extract_calls, stored):
    first = client.post("/items", files=_photo()).json()["id"]
    second = client.post("/items", files=_photo()).json()["id"]
    assert first != second


def test_items_sends_the_upload_unchanged_to_the_store_and_the_read(client, extract_calls, stored):
    """D9: the bytes stored are the bytes read, and the object's content type
    is the validated media type, not the client's header."""
    client.post("/items", files=_photo("image/jpeg; charset=binary"))
    ((_, data, media_type),) = stored["photo"]
    assert (data, media_type) == (PHOTO, "image/jpeg")
    assert extract_calls[0]["art"] == (PHOTO, "image/jpeg")


def test_items_stores_the_row(client, extract_calls, stored):
    client.post("/items", files=_photo())
    (row,) = stored["insert"]
    assert row["value_shown"] == "TESTCODE"
    assert row["reading"] == {
        "art_number_raw": "TESTCODE",
        "art_legible": "clear",
        "ambiguous_characters": [],
    }
    assert row["received_at"].tzinfo is not None
    assert stored["connect"] == 1


def test_items_empty_read_returns_null_and_stores_null(client, stored, monkeypatch):
    empty = _extraction("")
    empty.art_number_raw, empty.art_base, empty.legibility = None, None, "not_visible"
    monkeypatch.setattr(routes, "extract_bytes", lambda art, source="": empty)

    response = client.post("/items", files=_photo())
    assert response.status_code == 200
    assert response.json()["value_shown"] is None
    (row,) = stored["insert"]
    assert row["value_shown"] is None
    assert row["reading"]["art_legible"] == "not_visible"


@pytest.mark.parametrize(
    "revision", ["listing-tool-00007-zzz", None], ids=["on Cloud Run", "off Cloud Run"]
)
def test_items_stores_the_revision(client, extract_calls, stored, monkeypatch, revision):
    if revision is None:
        monkeypatch.delenv("K_REVISION", raising=False)
    else:
        monkeypatch.setenv("K_REVISION", revision)
    client.post("/items", files=_photo())
    assert stored["insert"][0]["revision"] == revision


@pytest.mark.parametrize(
    "files, status, detail",
    [
        pytest.param({}, 400, routes.NO_PHOTO, id="no photo"),
        pytest.param(
            {"art_photo": ("a.gif", io.BytesIO(b"x"), "image/gif")},
            400, routes.NOT_AN_IMAGE, id="wrong type",
        ),
        pytest.param(_upload_of(CAP + 1), 413, routes.TOO_LARGE, id="too large"),
    ],
)
def test_items_rejected_upload_stores_nothing(client, extract_calls, stored, files, status, detail):
    response = client.post("/items", files=files)
    assert response.status_code == status
    assert response.json() == {"detail": detail}  # fixed: never the client's media type
    assert stored["photo"] == [] and extract_calls == [] and stored["insert"] == []


RAW = "raw-error-text-that-must-not-leave"


def _fails(*args, **kwargs):
    raise TimeoutError(RAW)


@pytest.mark.parametrize(
    "step, target, detail",
    [
        ("photo", (routes.photos, "store_photo"), routes.PHOTO_NOT_SAVED),
        ("read", (routes, "extract_bytes"), routes.READ_FAILED),
        ("insert", (routes.db, "connect"), routes.READ_NOT_SAVED),
        ("insert", (routes.db, "insert_item"), routes.READ_NOT_SAVED),
    ],
    ids=["photo store", "read", "connect", "insert"],
)
def test_items_failure_is_a_502_with_a_fixed_message_and_one_log_line(
    client, extract_calls, stored, monkeypatch, caplog, step, target, detail
):
    monkeypatch.setattr(*target, _fails)
    with caplog.at_level(logging.ERROR, logger=routes.logger.name):
        response = client.post("/items", files=_photo())

    assert response.status_code == 502
    assert response.json() == {"detail": detail}
    assert RAW not in response.text

    (record,) = [r for r in caplog.records if r.name == routes.logger.name]
    assert record.getMessage() == f"POST /items failed: step={step} error=TimeoutError"
    assert RAW not in caplog.text

    # Decision order: nothing after the failed step runs.
    if step == "photo":
        assert extract_calls == []
    if step in ("photo", "read"):
        assert stored["insert"] == []


def test_the_reading_rebuilt_from_an_extraction_is_the_reading_read():
    """What the row stores replays: a reading through from_reading() and the
    rebuild comes back as the same reading."""
    original = ArtNumberReading(
        art_number_raw=s.SPLIT_SI_9,
        art_legible="partial",
        ambiguous_characters=[AmbiguousCharacter(position=5, reading="Q", alternative="O")],
    )
    extraction = from_reading(original, source="zz-item")
    assert ArtNumberReading.model_validate(routes._reading(extraction)) == original


# POST /items/{id}/confirm. The database is faked as for POST /items; what the
# confirm does to a row is tested against real Postgres in tests/test_db.py.

ITEM_ID = "6f1c2a3b-0000-4000-8000-00000000c0f1"


@pytest.fixture
def confirms(monkeypatch):
    """Fake database whose confirm_item answers `result`, recording each call."""
    calls = {"connect": 0, "confirm": [], "result": "confirmed"}

    @contextmanager
    def connect():
        calls["connect"] += 1
        yield "a connection"

    def confirm_item(conn, **kwargs):
        assert conn == "a connection"
        calls["confirm"].append(kwargs)
        return calls["result"]

    monkeypatch.setattr(routes.db, "connect", connect)
    monkeypatch.setattr(routes.db, "confirm_item", confirm_item)
    return calls


def _confirm(client, body, item_id: str = ITEM_ID):
    return client.post(f"/items/{item_id}/confirm", json=body)


def test_confirm_is_a_204_with_no_body(client, confirms):
    response = _confirm(client, {"final_value": s.SPLIT_SI_9})
    assert response.status_code == 204
    assert response.content == b""

    (call,) = confirms["confirm"]
    assert str(call["item_id"]) == ITEM_ID
    assert call["final_value"] == s.SPLIT_SI_9
    assert call["confirmed_at"].tzinfo is not None


def test_confirm_sends_the_final_value_as_entered(client, confirms):
    """D5: stored as entered; the trim and uppercase are only for the outcome."""
    entered = f" {s.SPLIT_SI_9.lower()}  "
    _confirm(client, {"final_value": entered})
    assert confirms["confirm"][0]["final_value"] == entered


def test_the_confirm_request_carries_only_the_final_value():
    """D5's build constraint: the value shown never comes from the client."""
    assert set(routes.ConfirmRequest.model_fields) == {"final_value"}


def test_an_extra_field_is_refused(client, confirms):
    response = _confirm(client, {"final_value": s.SPLIT_SI_9, "value_shown": s.SPLIT_SI_8})
    assert response.status_code == 400
    assert response.json() == {"detail": routes.INVALID_REQUEST}
    assert confirms["connect"] == 0


@pytest.mark.parametrize(
    "final_value, detail",
    [
        pytest.param("", routes.FINAL_VALUE_BLANK, id="empty"),
        pytest.param(" \t ", routes.FINAL_VALUE_BLANK, id="whitespace only"),
        pytest.param(s.GATE_UNREADABLE_MARK, routes.FINAL_VALUE_UNREADABLE, id="a ?"),
        pytest.param("?" + s.SPLIT_SI_9, routes.FINAL_VALUE_UNREADABLE, id="a leading ?"),
    ],
)
def test_a_blank_or_unreadable_final_value_is_refused_before_the_database(
    client, final_value, detail
):
    """D5. `no_real_stores` fails the test if the database is reached."""
    response = _confirm(client, {"final_value": final_value})
    assert response.status_code == 400
    assert response.json() == {"detail": detail}


@pytest.mark.parametrize(
    "result, status, detail",
    [
        pytest.param("empty_read", 400, routes.NOTHING_TO_CONFIRM, id="empty read"),
        pytest.param("not_found", 404, routes.ITEM_NOT_FOUND, id="unknown ID"),
        pytest.param("conflict", 409, routes.ALREADY_CONFIRMED, id="repeat, different value"),
    ],
)
def test_a_refused_confirm_has_a_fixed_message(client, confirms, result, status, detail):
    confirms["result"] = result
    response = _confirm(client, {"final_value": s.SPLIT_SI_9})
    assert response.status_code == status
    assert response.json() == {"detail": detail}
    assert s.SPLIT_SI_9 not in response.text


def test_the_empty_read_refusal_does_not_say_there_is_no_number():
    """ADR-0007, *Scope and storage*: an empty read must not tell staff that
    no ART number exists; the photo may just not show it. The wording itself
    is mvp-confirm's."""
    assert "ART number" not in routes.NOTHING_TO_CONFIRM


def test_a_repeat_with_the_same_value_succeeds_as_the_first_did(client, confirms):
    """D7, as amended: a lost response followed by a retap."""
    first = _confirm(client, {"final_value": s.SPLIT_SI_9})
    confirms["result"] = "repeated"
    second = _confirm(client, {"final_value": s.SPLIT_SI_9})
    assert (second.status_code, second.content) == (first.status_code, first.content)


@pytest.mark.parametrize("target", ["connect", "confirm_item"])
def test_confirm_database_failure_is_a_502_with_a_fixed_message_and_one_log_line(
    client, confirms, monkeypatch, caplog, target
):
    monkeypatch.setattr(routes.db, target, _fails)
    with caplog.at_level(logging.ERROR, logger=routes.logger.name):
        response = _confirm(client, {"final_value": s.SPLIT_SI_9})

    assert response.status_code == 502
    assert response.json() == {"detail": routes.CONFIRM_NOT_SAVED}
    assert RAW not in response.text

    (record,) = [r for r in caplog.records if r.name == routes.logger.name]
    assert record.getMessage() == (
        "POST /items/{id}/confirm failed: step=confirm error=TimeoutError"
    )
    assert RAW not in caplog.text and ITEM_ID not in caplog.text


# Validation errors, app-wide: 400 with a fixed message, never FastAPI's 422,
# whose body echoes the input.

SENT = s.SPLIT_SI_9


@pytest.mark.parametrize(
    "kwargs",
    [
        pytest.param({"json": {"value": SENT}}, id="missing field"),
        pytest.param({"json": {"final_value": [SENT]}}, id="wrong type"),
        pytest.param(
            {"content": f'{{"final_value": "{SENT}"', "headers": {"Content-Type": "application/json"}},
            id="not JSON",
        ),
    ],
)
def test_a_malformed_confirm_is_a_400_that_echoes_nothing(client, confirms, kwargs):
    response = client.post(f"/items/{ITEM_ID}/confirm", **kwargs)
    assert response.status_code == 400
    assert response.json() == {"detail": routes.INVALID_REQUEST}
    assert SENT not in response.text
    assert confirms["connect"] == 0


def test_a_confirm_on_an_id_that_is_not_a_uuid_is_a_400(client, confirms):
    response = _confirm(client, {"final_value": SENT}, item_id=f"zz-{SENT}")
    assert response.status_code == 400
    assert response.json() == {"detail": routes.INVALID_REQUEST}
    assert SENT not in response.text


def test_a_text_field_for_the_photo_is_a_400_that_echoes_nothing(client, extract_calls, stored):
    """POST /items takes a form upload: a plain text art_photo fails validation."""
    response = client.post("/items", data={"art_photo": SENT})
    assert response.status_code == 400
    assert response.json() == {"detail": routes.INVALID_REQUEST}
    assert SENT not in response.text
    assert stored["photo"] == [] and extract_calls == [] and stored["insert"] == []


def test_the_openapi_schema_documents_4xx_and_no_422(client):
    """mvp-scaffold generates types from this schema: it must describe what
    the server returns."""
    schema = client.app.openapi()
    operations = [op for ops in schema["paths"].values() for op in ops.values()]
    assert operations, "found no operations, so this test checked nothing"
    for op in operations:
        assert "422" not in op["responses"]
        (content,) = op["responses"]["4XX"]["content"].values()
        assert content["schema"] == {"$ref": "#/components/schemas/ErrorBody"}
    error_body = schema["components"]["schemas"]["ErrorBody"]
    assert error_body["properties"] == {"detail": {"type": "string", "title": "Detail"}}
    assert error_body["required"] == ["detail"]
