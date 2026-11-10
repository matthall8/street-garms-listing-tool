"""Capture label photos, run the pipeline, show the result.

Routes are plain `def`: the read uses run_sync, which can't run inside an
`async def` route (ADR-0008, D4).
"""

import base64
from dataclasses import asdict
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, File, Request, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from labels.pipeline import ACCEPTED, UnsupportedImageType, extract_bytes

MAX_UPLOAD_BYTES = 16 * 1024 * 1024  # phone photos are big

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
        raise UploadTooLarge("That photo is too large. The limit is 16MB.")
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
