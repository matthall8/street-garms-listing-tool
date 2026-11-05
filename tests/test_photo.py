"""EXIF orientation: every path sends the photo as a person sees it.

Images are built here with Pillow, so no real photo is needed. The path tests
stub get_art_agent rather than anything upstream, so the bytes they see are
the bytes read_art would send.
"""

from io import BytesIO
from types import SimpleNamespace

import pytest
from PIL import ExifTags, Image
from pydantic_ai.usage import RunUsage

import eval_transcription
from app import create_app
from labels import pipeline, transcribe
from labels.photo import upright
from labels.schemas import ArtNumberReading

ORIENTATION = ExifTags.Base.Orientation
WIDTH, HEIGHT = 40, 20
RED, WHITE = (255, 0, 0), (255, 255, 255)


def _image() -> Image.Image:
    """Landscape, white, with a red block in the stored top-left corner."""
    img = Image.new("RGB", (WIDTH, HEIGHT), WHITE)
    img.paste(RED, (0, 0, 10, 10))
    return img


def _encode(fmt: str, orientation: int | None = None) -> bytes:
    img, out, options = _image(), BytesIO(), {}
    if orientation is not None:
        exif = Image.Exif()
        exif[ORIENTATION] = orientation
        options["exif"] = exif.tobytes()
    if fmt == "MPO":  # two frames, as a camera writes it
        options.update(save_all=True, append_images=[_image()])
    img.save(out, format=fmt, **options)
    return out.getvalue()


def _is_red(pixel) -> bool:
    r, g, b = pixel[:3]
    return r > 200 and g < 60 and b < 60


class TestUntouched:
    @pytest.mark.parametrize("fmt, media_type", [
        ("JPEG", "image/jpeg"), ("PNG", "image/png"), ("WEBP", "image/webp"),
    ])
    def test_untagged_bytes_come_back_identical(self, fmt, media_type):
        data = _encode(fmt)
        assert upright(data, media_type) == (data, media_type)

    @pytest.mark.parametrize("orientation", [0, 1, 9])
    def test_orientation_outside_2_to_8_comes_back_identical(self, orientation):
        data = _encode("JPEG", orientation=orientation)
        assert upright(data, "image/jpeg") == (data, "image/jpeg")

    def test_unidentifiable_bytes_come_back_identical(self):
        assert upright(b"not-an-image", "image/heic") == (b"not-an-image", "image/heic")

    def test_other_errors_raise(self, monkeypatch):
        monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 10)  # 800 px > 2x the limit
        with pytest.raises(Image.DecompressionBombError):
            upright(_encode("JPEG", orientation=6), "image/jpeg")


class TestRotated:
    @pytest.mark.parametrize("fmt, media_type", [
        ("JPEG", "image/jpeg"), ("MPO", "image/jpeg"), ("PNG", "image/png"),
        ("WEBP", "image/webp"),
    ])
    def test_orientation_6_is_rotated_and_untagged(self, fmt, media_type):
        data = _encode(fmt, orientation=6)
        assert Image.open(BytesIO(data)).format == fmt, "fixture didn't build the format"

        out, out_type = upright(data, media_type)
        img = Image.open(BytesIO(out))
        assert out_type == media_type
        assert Image.MIME.get(img.format or "") == out_type, "media type doesn't match the bytes"
        assert img.size == (HEIGHT, WIDTH)
        assert img.getexif().get(ORIENTATION) is None
        # Orientation 6 is a quarter turn clockwise: stored top-left -> top-right.
        assert _is_red(img.getpixel((HEIGHT - 3, 3)))
        assert not _is_red(img.getpixel((3, 3)))

    def test_mpo_goes_out_as_jpeg_even_if_declared_mpo(self):
        _, out_type = upright(_encode("MPO", orientation=6), "image/mpo")
        assert out_type == "image/jpeg"


# --- Every path goes through the helper ----------------------------------

@pytest.fixture
def sent(monkeypatch):
    """Stub the agent; record the (bytes, media_type) each call would send."""
    calls = []

    def run_sync(messages):
        content = messages[1]
        calls.append((content.data, content.media_type))
        # The run result's fields read_art reads.
        return SimpleNamespace(
            output=ArtNumberReading(art_number_raw=None, art_legible="not_visible"),
            response=SimpleNamespace(model_name="test"), usage=RunUsage(requests=1))

    monkeypatch.setattr(transcribe, "get_art_agent", lambda model="": SimpleNamespace(run_sync=run_sync))
    return calls


def _assert_upright(calls):
    assert len(calls) == 1
    data, media_type = calls[0]
    assert media_type == "image/jpeg"
    assert Image.open(BytesIO(data)).size == (HEIGHT, WIDTH)


@pytest.fixture
def tagged_file(tmp_path):
    path = tmp_path / "label.jpg"
    path.write_bytes(_encode("JPEG", orientation=6))
    return path


def test_cli_path_sends_upright(sent, tagged_file):
    pipeline.extract(tagged_file)
    _assert_upright(sent)


def test_web_path_sends_upright(sent, monkeypatch):
    monkeypatch.setattr("dotenv.load_dotenv", lambda *args, **kwargs: False)
    app = create_app()
    app.config["TESTING"] = True
    response = app.test_client().post("/", data={
        "art_photo": (BytesIO(_encode("JPEG", orientation=6)), "label.jpg", "image/jpeg"),
    }, content_type="multipart/form-data")
    assert response.status_code == 200
    _assert_upright(sent)


def test_harness_path_sends_upright(sent, tagged_file):
    eval_transcription.get_art_number_reading(tagged_file, model="test")
    _assert_upright(sent)
