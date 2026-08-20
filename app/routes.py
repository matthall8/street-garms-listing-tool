"""Capture label photos, run the pipeline, show the result."""

import base64
from dataclasses import asdict

from flask import Blueprint, render_template, request

from labels.pipeline import extract_bytes

bp = Blueprint("main", __name__)

ACCEPTED = {"image/jpeg", "image/png", "image/webp", "image/heic", "image/heif"}


def _read(field: str):
    """Pull one upload off the form. Returns ((bytes, media_type), name) or None."""
    f = request.files.get(field)
    if not f or not f.filename:
        return None
    media_type = f.mimetype or "image/jpeg"
    if media_type not in ACCEPTED:
        raise ValueError(f"Unsupported image type: {media_type}")
    return (f.read(), media_type), f.filename


@bp.get("/")
def index():
    return render_template("index.html")


@bp.post("/")
def capture():
    try:
        art = _read("art_photo")
        details = _read("details_photo")
    except ValueError as exc:
        return render_template("index.html", error=str(exc)), 400

    if art is None and details is None:
        return render_template(
            "index.html", error="Add at least one photo — the ART number tag, the care label, or both."
        ), 400

    names = [n for n in (art and art[1], details and details[1]) if n]
    try:
        extraction = extract_bytes(
            art=art[0] if art else None,
            details=details[0] if details else None,
            source=", ".join(names),
        )
    except Exception as exc:  # surface failures in the page, not the console
        return render_template("index.html", error=f"Extraction failed: {exc}"), 502

    def preview(photo):
        if not photo:
            return None
        data, media_type = photo[0]
        return f"data:{media_type};base64,{base64.b64encode(data).decode()}"

    return render_template(
        "result.html",
        extraction=extraction,
        fields=asdict(extraction),
        art_preview=preview(art),
        details_preview=preview(details),
    )
