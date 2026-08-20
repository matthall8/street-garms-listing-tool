"""CLI entry point: transcribe and decode one garment care label."""

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from dotenv import load_dotenv

from labels.pipeline import extract


def cli() -> None:
    load_dotenv()

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "art_image",
        nargs="?",
        default="images/label.png",
        type=Path,
        help="photo of the ART number tag (default: images/label.png)",
    )
    ap.add_argument(
        "details_image",
        nargs="?",
        type=Path,
        help="optional photo of the care label (size, composition, origin)",
    )
    args = ap.parse_args()

    for image in (args.art_image, args.details_image):
        if image is not None and not image.is_file():
            ap.error(f"no such image: {image}")

    print(json.dumps(asdict(extract(args.art_image, args.details_image)), indent=2))


if __name__ == "__main__":
    cli()
