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
        "image",
        nargs="?",
        default="images/label.png",
        type=Path,
        help="path to a label photo (default: images/label.png)",
    )
    args = ap.parse_args()

    if not args.image.is_file():
        ap.error(f"no such image: {args.image}")

    print(json.dumps(asdict(extract(args.image)), indent=2))


if __name__ == "__main__":
    cli()
