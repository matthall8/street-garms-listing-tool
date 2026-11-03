"""CLI entry point: read and decode the ART number from one label photo."""

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from dotenv import load_dotenv

from labels.pipeline import UnsupportedImageType, extract


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
    args = ap.parse_args()

    if not args.art_image.is_file():
        ap.error(f"no such image: {args.art_image}")

    try:
        extraction = extract(args.art_image)
    except UnsupportedImageType as exc:
        ap.error(str(exc))
    print(json.dumps(asdict(extraction), indent=2))


if __name__ == "__main__":
    cli()
