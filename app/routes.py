"""Capture label photos, run the pipeline, show the result.

Routes are plain `def`: the read uses run_sync, which can't run inside an
`async def` route (ADR-0008, D4).
"""

import base64
import logging
import os
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, ConfigDict

from app import db, photos, sheet
from labels.pipeline import ACCEPTED, UnsupportedImageType, extract_bytes
from labels.schemas import ArtNumberReading, Extraction

MAX_UPLOAD_BYTES = 16 * 1024 * 1024  # phone photos are big

# POST /items failure bodies: fixed, never the raw error or the client's
# media type (ADR-0008, D3).
NO_PHOTO = "Add a photo of the label showing the ART number."
NOT_AN_IMAGE = "That file isn't a photo we can read. Use a JPEG, PNG or WebP."
TOO_LARGE = "That photo is too large. The limit is 16MB."
PHOTO_NOT_SAVED = "The photo couldn't be saved. Try again."
READ_FAILED = "The label couldn't be read. Try again."
READ_NOT_SAVED = "The read couldn't be saved. Try again."

# POST /items/{id}/confirm failure bodies: fixed, never the value sent.
FINAL_VALUE_BLANK = "Enter the ART number."
FINAL_VALUE_UNREADABLE = "Replace each ? with the character on the label."
NOTHING_TO_CONFIRM = "There's no read to confirm. Upload the photo again."
ITEM_NOT_FOUND = "That item wasn't found. Upload the photo again."
ALREADY_CONFIRMED = "This item was already confirmed with a different ART number."
CONFIRM_NOT_SAVED = "The confirm couldn't be saved. Try again."

# POST /items/{id}/post-to-sheet failure bodies; an unknown ID is
# ITEM_NOT_FOUND. An empty read is never confirmed, so it gets NOT_CONFIRMED,
# which mustn't say there's no ART number.
NOT_CONFIRMED = "This item hasn't been confirmed, so there's nothing to post."
FINAL_VALUE_NOT_LOADED = "The confirmed value couldn't be loaded. Try again."

# Any route's malformed request: FastAPI's default 422 echoes the input.
INVALID_REQUEST = "The request wasn't valid."


class ErrorBody(BaseModel):
    """An error response's whole body: one fixed message."""

    detail: str


logger = logging.getLogger(__name__)
# "4XX" also drops FastAPI's 422 from the schema: the handler below answers
# 400 (fastapi/openapi/utils.py adds a 422 only when a route has none of
# "422", "4XX" or "default"). GET / and POST / answer HTML, not this body,
# until mvp-cutover deletes them.
router = APIRouter(responses={"4XX": {"model": ErrorBody}})
templates = Jinja2Templates(directory=Path(__file__).parent / "templates")


class UploadTooLarge(Exception):
    pass


def _too_large(f: UploadFile) -> bool:
    """Whether an upload is over the cap. An unknown size counts as over."""
    return f.size is None or f.size > MAX_UPLOAD_BYTES


def _read(f: UploadFile | None):
    """Pull the upload off the form. Returns ((bytes, media_type), name) or None."""
    if f is None or not f.filename:
        return None
    if _too_large(f):
        raise UploadTooLarge(TOO_LARGE)
    # content_type is the raw header, which can carry parameters after a `;`.
    media_type = (f.content_type or "").split(";")[0].strip().lower() or "image/jpeg"
    if media_type not in ACCEPTED:
        raise UnsupportedImageType(f"Unsupported image type: {media_type}")
    return (f.file.read(), media_type), f.filename


def _form_error(request: Request, message: str, status_code: int):
    return templates.TemplateResponse(
        request, "index.html", {"error": message}, status_code=status_code
    )


@router.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse(request, "index.html")


@router.post("/", response_class=HTMLResponse)
def capture(request: Request, art_photo: Annotated[UploadFile | None, File()] = None):
    try:
        art = _read(art_photo)
    except UnsupportedImageType as exc:
        return _form_error(request, str(exc), 400)
    except UploadTooLarge as exc:
        return _form_error(request, str(exc), 413)

    if art is None:
        return _form_error(request, "Add a photo of the label showing the ART number.", 400)

    (data, media_type), name = art
    try:
        extraction = extract_bytes(art=(data, media_type), source=name)
    except Exception as exc:  # surface failures in the page, not the console
        return _form_error(request, f"Extraction failed: {exc}", 502)

    return templates.TemplateResponse(
        request,
        "result.html",
        {
            "extraction": extraction,
            "fields": asdict(extraction),
            "art_preview": f"data:{media_type};base64,{base64.b64encode(data).decode()}",
        },
    )


class ItemCreated(BaseModel):
    """POST /items' whole response: anything else the read found stays on the
    server (ADR-0008, D3, D4). value_shown is None for an empty read."""

    id: UUID
    value_shown: str | None


class SheetOutcome(BaseModel):
    """The whole response of a confirm and of Post to Sheet (ADR-0008, D7):
    `sent` when the append succeeded, `failed` when it raised or wasn't 2xx
    (a timed-out one may still have landed), `unknown` for a repeated
    confirm, which makes no append."""

    sheet: Literal["sent", "failed", "unknown"]


def _log_failure(route: str, step: str, exc: Exception) -> None:
    """One line per failed request: the route's template (never the item ID),
    the step and the exception's class, never its message, which can carry
    values (ADR-0009, D3)."""
    logger.error("%s failed: step=%s error=%s", route, step, type(exc).__name__)


def _append(route: str, final_value: str) -> SheetOutcome:
    """Append the final value to the Sheet. A failure is an outcome, not an
    error: a confirm is already saved by then, so the route still answers 200
    (ADR-0008, D7, as amended 2026-11-19)."""
    try:
        sheet.add_to_sheet(final_value)
    except Exception as exc:
        _log_failure(route, "sheets", exc)
        return SheetOutcome(sheet="failed")
    return SheetOutcome(sheet="sent")


def _reading(extraction: Extraction) -> dict:
    """The model's read, rebuilt from the Extraction in ArtNumberReading's
    shape, so the eval replay can load it and run it through from_reading().
    model_validate, not the constructor: it checks legibility against the
    model's values at runtime, where Extraction only types it as str."""
    return ArtNumberReading.model_validate(
        {
            "art_number_raw": extraction.art_number_raw,
            "art_legible": extraction.legibility,
            "ambiguous_characters": extraction.all_reads,
        }
    ).model_dump()


@router.post("/items", response_model=ItemCreated)
def create_item(art_photo: Annotated[UploadFile | None, File()] = None):
    """Validate, store the photo, read, then insert the row. A rejected upload
    stores nothing; a failure at any later step is a failed read, a 502
    (ADR-0008, D5)."""
    item_id = uuid4()
    received_at = datetime.now(UTC)
    try:
        art = _read(art_photo)
    except UnsupportedImageType:
        raise HTTPException(status_code=400, detail=NOT_AN_IMAGE) from None
    except UploadTooLarge:
        raise HTTPException(status_code=413, detail=TOO_LARGE) from None
    if art is None:
        raise HTTPException(status_code=400, detail=NO_PHOTO)

    (data, media_type), _ = art  # the client's filename is unused: source is the item ID

    try:
        photos.store_photo(item_id, data, media_type)
    except Exception as exc:
        _log_failure("POST /items", "photo", exc)
        raise HTTPException(status_code=502, detail=PHOTO_NOT_SAVED) from None

    try:
        extraction = extract_bytes(art=(data, media_type), source=str(item_id))
        reading = _reading(extraction)
    except Exception as exc:
        _log_failure("POST /items", "read", exc)
        raise HTTPException(status_code=502, detail=READ_FAILED) from None

    try:
        with db.connect() as conn:
            db.insert_item(
                conn,
                item_id=item_id,
                received_at=received_at,
                revision=os.environ.get("K_REVISION"),  # NULL off Cloud Run
                reading=reading,
                value_shown=extraction.art_base,
            )
    except Exception as exc:
        _log_failure("POST /items", "insert", exc)  # the photo stays, orphaned (ADR-0008, D5)
        raise HTTPException(status_code=502, detail=READ_NOT_SAVED) from None

    return ItemCreated(id=item_id, value_shown=extraction.art_base)


class ConfirmRequest(BaseModel):
    """POST /items/{id}/confirm's whole request: the final value as entered.
    The value shown is never taken from the client (ADR-0008, D5)."""

    model_config = ConfigDict(extra="forbid")

    final_value: str


@router.post("/items/{item_id}/confirm", response_model=SheetOutcome)
def confirm_item(item_id: UUID, body: ConfirmRequest) -> SheetOutcome:
    """Record the final value; the server works out unchanged or edited
    (ADR-0008, D5). Then append it to the Sheet: `sent` or `failed`. A repeat
    with the same final value succeeds again, after a lost response, but makes
    no append and answers `unknown`; with a different one it is refused, and
    changes nothing (D7, as amended 2026-11-19)."""
    final_value = body.final_value
    # Before any database call. strip() trims more than D5's spaces: stricter
    # here is fine, and the outcome uses D5's comparison, in app/db.py.
    if not final_value.strip():
        raise HTTPException(status_code=400, detail=FINAL_VALUE_BLANK)
    if "?" in final_value:
        raise HTTPException(status_code=400, detail=FINAL_VALUE_UNREADABLE)

    try:
        with db.connect() as conn:
            result = db.confirm_item(
                conn, item_id=item_id, final_value=final_value, confirmed_at=datetime.now(UTC)
            )
    except Exception as exc:
        _log_failure("POST /items/{id}/confirm", "confirm", exc)
        raise HTTPException(status_code=502, detail=CONFIRM_NOT_SAVED) from None

    # After the connection closes: an append that hangs doesn't hold it.
    match result:
        case "confirmed":
            return _append("POST /items/{id}/confirm", final_value)
        case "repeated":
            return SheetOutcome(sheet="unknown")
        case "empty_read":
            raise HTTPException(status_code=400, detail=NOTHING_TO_CONFIRM)
        case "not_found":
            raise HTTPException(status_code=404, detail=ITEM_NOT_FOUND)
        case "conflict":
            raise HTTPException(status_code=409, detail=ALREADY_CONFIRMED)


@router.post("/items/{item_id}/post-to-sheet", response_model=SheetOutcome)
def post_to_sheet(item_id: UUID) -> SheetOutcome:
    """Append a confirmed item's stored final value to the Sheet again: `sent`
    or `failed`. No body, so no value from the request can reach the Sheet. It
    checks no Sheet state, so it never refuses a second append (ADR-0008, D7,
    as amended 2026-11-19)."""
    try:
        with db.connect() as conn:
            result = db.confirmed_final_value(conn, item_id=item_id)
    except Exception as exc:
        _log_failure("POST /items/{id}/post-to-sheet", "load", exc)
        raise HTTPException(status_code=502, detail=FINAL_VALUE_NOT_LOADED) from None

    # After the connection closes, as in confirm_item.
    match result:
        case ("confirmed", final_value):
            return _append("POST /items/{id}/post-to-sheet", final_value)
        case ("unconfirmed", _):
            raise HTTPException(status_code=409, detail=NOT_CONFIRMED)
        case ("not_found", _):
            raise HTTPException(status_code=404, detail=ITEM_NOT_FOUND)


def invalid_request(request: Request, exc: Exception) -> JSONResponse:
    """Every route's RequestValidationError: a 400 with a fixed message, never
    FastAPI's 422, whose body echoes what was sent. Registered in
    create_app()."""
    return JSONResponse(status_code=400, content={"detail": INVALID_REQUEST})