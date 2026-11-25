"""Write the API's OpenAPI schema to frontend/openapi.json.

Run after any change to a route or its models, then regenerate the
frontend's types from the file. No network, no API key.

    python tests/generate_openapi.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import create_app

SCHEMA_PATH = Path(__file__).resolve().parent.parent / "frontend" / "openapi.json"


def create_schema() -> str:
    schema = create_app().openapi()
    formatted_schema = json.dumps(schema, indent=2)
    final_schema = formatted_schema + "\n"
    return final_schema


if __name__ == "__main__":
    SCHEMA_PATH.write_text(create_schema())
