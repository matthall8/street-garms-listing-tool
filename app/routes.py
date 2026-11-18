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
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from app import db, photos
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

logger = logging.getLogger(__name__)
router = APIRouter()
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


def _log_failure(step: str, exc: Exception) -> None:
    """One line per failed POST /items: the step and the exception's class,
    never its message, which can carry values (ADR-0009, D3)."""
    logger.error("POST /items failed: step=%s error=%s", step, type(exc).__name__)


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
        _log_failure("photo", exc)
        raise HTTPException(status_code=502, detail=PHOTO_NOT_SAVED) from None

    try:
        extraction = extract_bytes(art=(data, media_type), source=str(item_id))
        reading = _reading(extraction)
    except Exception as exc:
        _log_failure("read", exc)
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
        _log_failure("insert", exc)  # the photo stays, orphaned (ADR-0008, D5)
        raise HTTPException(status_code=502, detail=READ_NOT_SAVED) from None

    return ItemCreated(id=item_id, value_shown=extraction.art_base)

