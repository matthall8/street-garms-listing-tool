"""Capture a label photo, run the pipeline, show the result."""

import base64
from dataclasses import asdict

from flask import Blueprint, render_template, request

from labels.pipeline import extract_bytes

bp = Blueprint("main", __name__)

ACCEPTED = {"image/jpeg", "image/png", "image/webp", "image/heic", "image/heif"}


@bp.get("/")
def index():
    return render_template("index.html")


@bp.post("/")
def capture():
    photo = request.files.get("photo")
    if not photo or not photo.filename:
        return render_template("index.html", error="Choose or take a photo first."), 400

    media_type = photo.mimetype or "image/jpeg"
    if media_type not in ACCEPTED:
        return render_template(
            "index.html", error=f"Unsupported image type: {media_type}"
        ), 400

    data = photo.read()
    try:
        extraction = extract_bytes(data, media_type, photo.filename)
    except Exception as exc:  # surface failures in the page, not the console
        return render_template("index.html", error=f"Extraction failed: {exc}"), 502

    preview = f"data:{media_type};base64,{base64.b64encode(data).decode()}"
    return render_template(
        "result.html",
        extraction=extraction,
        fields=asdict(extraction),
        preview=preview,
    )
