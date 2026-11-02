"""Send the photo as a person sees it: apply the EXIF orientation tag.

Browsers and Finder rotate a photo by its tag; the API doesn't. Upright is
judged as the model receives it (ADR-0002), so a tagged photo is rotated here.
An untagged one goes out byte-for-byte: re-saving it would re-encode it and
change what the model sees without showing in the harness's photo_hashes.
"""

from io import BytesIO

from PIL import ExifTags, Image, ImageOps, UnidentifiedImageError

# Pillow format -> (save format, media type). Only types the API accepts.
# Pillow opens many iPhone and camera JPEGs as MPO; they go out as JPEG.
_SAVE_AS = {
    "JPEG": ("JPEG", "image/jpeg"),
    "MPO": ("JPEG", "image/jpeg"),
    "PNG": ("PNG", "image/png"),
    "WEBP": ("WEBP", "image/webp"),
}


def upright(data: bytes, media_type: str) -> tuple[bytes, str]:
    """The photo rotated by its orientation tag, as (bytes, media_type).

    Untagged, orientation 1 or outside 2–8, a format with no entry above, or
    bytes Pillow can't identify: returned unchanged, for the API to accept or
    reject as before. Reading the tag doesn't decode the pixels, so this stays
    cheap.
    """
    try:
        img = Image.open(BytesIO(data))
    except UnidentifiedImageError:
        return data, media_type
    if img.getexif().get(ExifTags.Base.Orientation) not in range(2, 9) or img.format not in _SAVE_AS:
        return data, media_type

    save_format, out_type = _SAVE_AS[img.format]
    rotated = ImageOps.exif_transpose(img)
    options: dict = {"quality": 95} if save_format in ("JPEG", "WEBP") else {}
    if icc := img.info.get("icc_profile"):
        options["icc_profile"] = icc
    out = BytesIO()
    rotated.save(out, format=save_format, **options)
    return out.getvalue(), out_type
