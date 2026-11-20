"""The FastAPI routes: uploads in, status codes and pages out.

Every test here runs offline. Two guards keep it that way:

- `client` stops create_app() loading .env, rather than deleting the API key
  afterwards. monkeypatch restores whatever it deletes when a test ends, so
  deleting a key that .env just loaded would hand it to every later test.
- `no_real_extraction` makes any test that reaches the pipeline unpatched fail
  by name. It uses pytest.fail because the route's `except Exception` would
  swallow an ordinary exception into a normal-looking 502.
- `no_real_stores` does the same for the photo store, the database and the
  Sheet.

The patch target is app.routes.extract_bytes, NOT labels.pipeline.extract_bytes
— routes.py does `from labels.pipeline import extract_bytes`, which binds the
name at import time, so patching the source module would have no effect.
"""

import inspect
import io
import logging
import os
import struct
import zlib
from contextlib import contextmanager

import pytest
from fastapi import FastAPI, UploadFile
from fastapi.routing import APIRoute, iter_route_contexts
from fastapi.testclient import TestClient
from PIL import Image

from app import create_app, routes
from app.errors import SERVER_ERROR
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


def _image(fmt: str, size: tuple[int, int] = (4, 4), mode: str = "RGB", **options) -> bytes:
    """A real image, built at runtime as tests/test_photo.py does."""
    out = io.BytesIO()
    Image.new(mode, size).save(out, format=fmt, **options)
    return out.getvalue()


# One real tiny image per accepted type: the upload checks open every upload.
IMAGES = {"image/jpeg": _image("JPEG"), "image/png": _image("PNG"), "image/webp": _image("WEBP")}


def _upload(filename: str, media_type: str) -> dict:
    """A real image of the declared type; fake bytes for a type the checks
    refuse before opening it."""
    data = IMAGES.get(media_type.split(";")[0], b"x")
    return {"art_photo": (filename, io.BytesIO(data), media_type)}


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
        {"art": (IMAGES[media_type], media_type), "source": filename}
    ]
    assert b"Test Jacket" in response.content


def test_a_stray_second_photo_is_ignored(client, extract_calls):
    """The form has one upload box; a details_photo field from an old form or
    a script never reaches the pipeline."""
    files = _upload("a.png", "image/png")
    files["details_photo"] = ("b.png", io.BytesIO(b"y"), "image/png")
    response = client.post("/", files=files)
    assert response.status_code == 200
    assert extract_calls == [{"art": (IMAGES["image/png"], "image/png"), "source": "a.png"}]


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
    assert extract_calls == [{"art": (IMAGES["image/jpeg"], "image/jpeg"), "source": "label.jpg"}]


CAP = 7_500_000  # the API's 10,000,000 base64 bytes, as raw bytes


def _upload_of(size: int) -> dict:
    """Fake bytes: the size check runs before anything opens them."""
    return {"art_photo": ("a.png", io.BytesIO(b"x" * size), "image/png")}


def _chunk(kind: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))


def _png_of(size: int) -> bytes:
    """A real PNG of exactly `size` bytes: a tiny one, padded before IEND with
    a private ancillary chunk with a correct CRC, so it passes verify()."""
    png = _image("PNG")
    body, iend = png[:-12], png[-12:]  # IEND is the last 12 bytes
    padding = size - len(png) - 12  # a chunk's length, type and CRC
    return body + _chunk(b"paDd", b"\0" * padding) + iend


def test_upload_at_the_cap_reaches_the_pipeline(client, extract_calls):
    photo = _png_of(CAP)
    assert len(photo) == CAP
    response = client.post("/", files={"art_photo": ("a.png", io.BytesIO(photo), "image/png")})
    assert response.status_code == 200
    assert extract_calls[0]["art"] == (photo, "image/png")


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

PHOTO = _image("JPEG", size=(6, 5))  # differs from IMAGES' JPEG


@pytest.fixture(autouse=True)
def no_real_stores(monkeypatch):
    def unpatched(*args, **kwargs):
        pytest.fail("a photo store, database or Sheet call was not patched")

    monkeypatch.setattr(routes.photos, "store_photo", unpatched)
    monkeypatch.setattr(routes.db, "connect", unpatched)
    monkeypatch.setattr(routes.db, "insert_item", unpatched)
    monkeypatch.setattr(routes.db, "confirm_item", unpatched)
    monkeypatch.setattr(routes.db, "confirmed_final_value", unpatched)
    monkeypatch.setattr(routes.sheet, "add_to_sheet", unpatched)


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


def _photo(media_type: str = "image/jpeg", data: bytes = PHOTO) -> dict:
    return {"art_photo": ("label.jpg", io.BytesIO(data), media_type)}


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


def _broken_png() -> bytes:
    """A PNG that opens but fails verify(): IDAT's CRC is wrong, and opening
    reads only up to IDAT."""
    png = bytearray(_image("PNG"))
    at = png.index(b"IDAT")
    (length,) = struct.unpack(">I", png[at - 4 : at])
    png[at + 4 + length] ^= 0xFF
    return bytes(png)


def test_the_broken_png_opens_and_fails_verify():
    """Guards the rejection test below: it's verify() that refuses it."""
    with Image.open(io.BytesIO(_broken_png())) as img:
        assert img.format == "PNG"
        with pytest.raises(SyntaxError):
            img.verify()


def _mpo() -> bytes:
    data = _image("MPO", save_all=True, append_images=[Image.new("RGB", (4, 4))])
    with Image.open(io.BytesIO(data)) as img:
        assert img.format == "MPO"
    return data


def _without_content_type(data: bytes) -> dict:
    """Multipart kwargs for a photo part with no Content-Type header. Built by
    hand because httpx fills one in."""
    body = (
        b"--b\r\n"
        b'Content-Disposition: form-data; name="art_photo"; filename="label"\r\n\r\n'
        + data
        + b"\r\n--b--\r\n"
    )
    return {"content": body, "headers": {"Content-Type": "multipart/form-data; boundary=b"}}


@pytest.mark.parametrize(
    "data, media_type, status, detail",
    [
        pytest.param(
            _image("PNG", size=(8001, 1), mode="1"), "image/png", 413, routes.TOO_LARGE,
            id="wider than 8000 px",
        ),
        pytest.param(
            _image("PNG", size=(1, 8001), mode="1"), "image/png", 413, routes.TOO_LARGE,
            id="taller than 8000 px",
        ),
        pytest.param(_broken_png(), "image/png", 400, routes.NOT_AN_IMAGE, id="fails verify"),
        pytest.param(
            IMAGES["image/png"], "image/jpeg", 400, routes.NOT_AN_IMAGE, id="png declared jpeg"
        ),
        pytest.param(
            IMAGES["image/jpeg"], "image/webp", 400, routes.NOT_AN_IMAGE, id="jpeg declared webp"
        ),
        pytest.param(b"x", "image/jpeg", 400, routes.NOT_AN_IMAGE, id="not an image"),
    ],
)
def test_items_image_check_rejects_and_stores_nothing(
    client, extract_calls, stored, data, media_type, status, detail
):
    response = client.post("/items", files=_photo(media_type, data))
    assert response.status_code == status
    assert response.json() == {"detail": detail}
    assert stored["photo"] == [] and extract_calls == [] and stored["insert"] == []


def test_items_decompression_bomb_is_a_413_and_stores_nothing(
    client, extract_calls, stored, monkeypatch
):
    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 10)  # PHOTO's 30 px > 2x the limit
    response = client.post("/items", files=_photo())
    assert response.status_code == 413
    assert response.json() == {"detail": routes.TOO_LARGE}
    assert stored["photo"] == [] and extract_calls == [] and stored["insert"] == []


@pytest.mark.parametrize(
    "data, media_type",
    [
        pytest.param(_mpo(), "image/jpeg", id="mpo declared jpeg"),
        pytest.param(_image("PNG", size=(8000, 1), mode="1"), "image/png", id="8000 px wide"),
        pytest.param(_image("PNG", size=(1, 8000), mode="1"), "image/png", id="8000 px tall"),
    ],
)
def test_items_image_check_accepts(client, extract_calls, stored, data, media_type):
    response = client.post("/items", files=_photo(media_type, data))
    assert response.status_code == 200
    assert stored["photo"][0][1:] == (data, media_type)
    assert extract_calls[0]["art"] == (data, media_type)


def test_items_no_content_type_is_taken_as_jpeg(client, extract_calls, stored):
    response = client.post("/items", **_without_content_type(PHOTO))
    assert response.status_code == 200
    assert extract_calls[0]["art"] == (PHOTO, "image/jpeg")


def test_items_no_content_type_on_another_format_is_not_an_image(client, extract_calls, stored):
    response = client.post("/items", **_without_content_type(IMAGES["image/png"]))
    assert response.status_code == 400
    assert response.json() == {"detail": routes.NOT_AN_IMAGE}
    assert stored["photo"] == [] and extract_calls == []


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
    """Fake database whose confirm_item answers `result`, and a fake Sheet
    whose append succeeds, recording each call and each value appended."""
    calls = {"connect": 0, "confirm": [], "result": "confirmed", "appended": []}

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
    monkeypatch.setattr(routes.sheet, "add_to_sheet", calls["appended"].append)
    return calls


def _confirm(client, body, item_id: str = ITEM_ID):
    return client.post(f"/items/{item_id}/confirm", json=body)


def test_a_first_confirm_appends_once_and_answers_sent(client, confirms):
    response = _confirm(client, {"final_value": s.SPLIT_SI_9})
    assert response.status_code == 200
    assert response.json() == {"sheet": "sent"}
    assert confirms["appended"] == [s.SPLIT_SI_9]

    (call,) = confirms["confirm"]
    assert str(call["item_id"]) == ITEM_ID
    assert call["final_value"] == s.SPLIT_SI_9
    assert call["confirmed_at"].tzinfo is not None


def test_confirm_sends_the_final_value_as_entered(client, confirms):
    """D5: stored as entered, and appended as stored; the trim and uppercase
    are only for the outcome."""
    entered = f" {s.SPLIT_SI_9.lower()}  "
    _confirm(client, {"final_value": entered})
    assert confirms["confirm"][0]["final_value"] == entered
    assert confirms["appended"] == [entered]


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
    assert confirms["appended"] == []


def test_the_empty_read_refusal_does_not_say_there_is_no_number():
    """ADR-0007, *Scope and storage*: an empty read must not tell staff that
    no ART number exists; the photo may just not show it. The wording itself
    is mvp-confirm's."""
    assert "ART number" not in routes.NOTHING_TO_CONFIRM


def test_a_repeat_with_the_same_value_makes_no_append_and_answers_unknown(client, confirms):
    """D7, as amended: a lost response followed by a retap. The first confirm
    may or may not have reached the Sheet, so the repeat says neither."""
    first = _confirm(client, {"final_value": s.SPLIT_SI_9})
    confirms["result"] = "repeated"
    second = _confirm(client, {"final_value": s.SPLIT_SI_9})
    assert (first.status_code, first.json()) == (200, {"sheet": "sent"})
    assert (second.status_code, second.json()) == (200, {"sheet": "unknown"})
    assert confirms["appended"] == [s.SPLIT_SI_9]


def test_a_failed_append_answers_failed_and_logs_one_line(client, confirms, monkeypatch, caplog):
    """D7, as amended: the confirm stands, so a 200; the screen handles
    `failed`. The log line has the step and the class, never the value."""
    monkeypatch.setattr(routes.sheet, "add_to_sheet", _fails)
    with caplog.at_level(logging.ERROR, logger=routes.logger.name):
        response = _confirm(client, {"final_value": s.SPLIT_SI_9})

    assert (response.status_code, response.json()) == (200, {"sheet": "failed"})
    assert len(confirms["confirm"]) == 1
    (record,) = [r for r in caplog.records if r.name == routes.logger.name]
    assert record.getMessage() == (
        "POST /items/{id}/confirm failed: step=sheets error=TimeoutError"
    )
    for leak in (RAW, s.SPLIT_SI_9, ITEM_ID):
        assert leak not in caplog.text


def test_an_unhandled_exception_is_a_json_500_and_one_log_line(client, confirms, monkeypatch, caplog):
    """app/errors.py: _append runs outside any try in confirm_item, so its
    exception is unhandled. One record, with the route's template and the
    class: no traceback, message, value or item ID, from any logger."""

    def raises(route, final_value):
        raise RuntimeError(f"{RAW} {ITEM_ID} {final_value}")

    monkeypatch.setattr(routes, "_append", raises)
    unraised = TestClient(client.app, raise_server_exceptions=False)
    # WARNING: the test client's own httpx line, at INFO, has the raw path.
    with caplog.at_level(logging.WARNING):
        response = _confirm(unraised, {"final_value": s.SPLIT_SI_9})

    assert response.status_code == 500
    assert response.json() == {"detail": SERVER_ERROR}
    (record,) = caplog.records
    assert record.name == "app.errors"
    assert record.getMessage() == "POST /items/{item_id}/confirm failed: error=RuntimeError"
    assert record.exc_info is None and record.exc_text is None
    for leak in (RAW, s.SPLIT_SI_9, ITEM_ID, "Traceback"):
        assert leak not in caplog.text
        assert leak not in response.text


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
    assert confirms["appended"] == []


# POST /items/{id}/post-to-sheet. The read is faked; what it returns for each
# kind of row is tested against real Postgres in tests/test_db.py.

STORED = "0" + s.SPLIT_SI_9  # a leading zero, as staff might type it


@pytest.fixture
def posts(monkeypatch):
    """Fake database whose confirmed_final_value answers `result`, and a fake
    Sheet whose append succeeds, recording each call and each value appended."""
    calls = {"connect": 0, "load": [], "result": ("confirmed", STORED), "appended": []}

    @contextmanager
    def connect():
        calls["connect"] += 1
        yield "a connection"

    def confirmed_final_value(conn, **kwargs):
        assert conn == "a connection"
        calls["load"].append(kwargs)
        return calls["result"]

    monkeypatch.setattr(routes.db, "connect", connect)
    monkeypatch.setattr(routes.db, "confirmed_final_value", confirmed_final_value)
    monkeypatch.setattr(routes.sheet, "add_to_sheet", calls["appended"].append)
    return calls


def _post(client, item_id: str = ITEM_ID, **kwargs):
    return client.post(f"/items/{item_id}/post-to-sheet", **kwargs)


def test_post_to_sheet_appends_the_stored_value_and_answers_sent(client, posts):
    response = _post(client)
    assert (response.status_code, response.json()) == (200, {"sheet": "sent"})
    (call,) = posts["load"]
    assert str(call["item_id"]) == ITEM_ID
    assert posts["appended"] == [STORED]


def test_post_to_sheet_takes_no_body():
    """D7's build constraint, as amended: no value from the request can reach
    the Sheet, because the route takes none."""
    assert list(inspect.signature(routes.post_to_sheet).parameters) == ["item_id"]


def test_post_to_sheet_ignores_a_value_sent_anyway(client, posts):
    response = _post(client, json={"final_value": s.SPLIT_SI_8})
    assert (response.status_code, response.json()) == (200, {"sheet": "sent"})
    assert posts["appended"] == [STORED]


def test_post_to_sheet_never_refuses_a_second_append(client, posts):
    """It checks no Sheet state: staff check the Sheet first (mvp-confirm)."""
    assert [_post(client).json() for _ in range(2)] == [{"sheet": "sent"}] * 2
    assert posts["appended"] == [STORED, STORED]


def test_post_to_sheet_failed_append_answers_failed_and_logs_one_line(
    client, posts, monkeypatch, caplog
):
    monkeypatch.setattr(routes.sheet, "add_to_sheet", _fails)
    with caplog.at_level(logging.ERROR, logger=routes.logger.name):
        response = _post(client)

    assert (response.status_code, response.json()) == (200, {"sheet": "failed"})
    (record,) = [r for r in caplog.records if r.name == routes.logger.name]
    assert record.getMessage() == (
        "POST /items/{id}/post-to-sheet failed: step=sheets error=TimeoutError"
    )
    for leak in (RAW, STORED, ITEM_ID):
        assert leak not in caplog.text


@pytest.mark.parametrize(
    "result, status, detail",
    [
        pytest.param(("unconfirmed", None), 409, routes.NOT_CONFIRMED, id="unconfirmed or empty read"),
        pytest.param(("not_found", None), 404, routes.ITEM_NOT_FOUND, id="unknown ID"),
    ],
)
def test_post_to_sheet_refusal_has_a_fixed_message_and_makes_no_append(
    client, posts, result, status, detail
):
    posts["result"] = result
    response = _post(client)
    assert (response.status_code, response.json()) == (status, {"detail": detail})
    assert posts["appended"] == []


def test_the_not_confirmed_refusal_does_not_say_there_is_no_number():
    """As the confirm's empty-read refusal: an empty read lands here too."""
    assert "ART number" not in routes.NOT_CONFIRMED


@pytest.mark.parametrize("target", ["connect", "confirmed_final_value"])
def test_post_to_sheet_database_failure_is_a_502_with_one_log_line(
    client, posts, monkeypatch, caplog, target
):
    monkeypatch.setattr(routes.db, target, _fails)
    with caplog.at_level(logging.ERROR, logger=routes.logger.name):
        response = _post(client)

    assert response.status_code == 502
    assert response.json() == {"detail": routes.FINAL_VALUE_NOT_LOADED}
    assert RAW not in response.text
    (record,) = [r for r in caplog.records if r.name == routes.logger.name]
    assert record.getMessage() == (
        "POST /items/{id}/post-to-sheet failed: step=load error=TimeoutError"
    )
    assert RAW not in caplog.text and ITEM_ID not in caplog.text
    assert posts["appended"] == []


def test_post_to_sheet_on_an_id_that_is_not_a_uuid_is_a_400(client, posts):
    response = _post(client, item_id=f"zz-{s.SPLIT_SI_9}")
    assert response.status_code == 400
    assert response.json() == {"detail": routes.INVALID_REQUEST}
    assert s.SPLIT_SI_9 not in response.text
    assert posts["connect"] == 0


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


def test_the_openapi_schema_documents_the_sheet_outcome_on_both_routes(client):
    """mvp-confirm's types come from this: `sheet` and its three values."""
    schema = client.app.openapi()
    for path in ("/items/{item_id}/confirm", "/items/{item_id}/post-to-sheet"):
        (content,) = schema["paths"][path]["post"]["responses"]["200"]["content"].values()
        assert content["schema"] == {"$ref": "#/components/schemas/SheetOutcome"}
    assert "requestBody" not in schema["paths"]["/items/{item_id}/post-to-sheet"]["post"]
    outcome = schema["components"]["schemas"]["SheetOutcome"]
    assert outcome["properties"]["sheet"]["enum"] == ["sent", "failed", "unknown"]
    assert outcome["required"] == ["sheet"]
