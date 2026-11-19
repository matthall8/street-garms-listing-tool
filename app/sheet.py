import os
from functools import cache

import google.auth
from google.auth.transport.requests import AuthorizedSession

# One append of one short row, Cloud Run to the Sheets API: normally well
# under a second, so a call still going after this is hung. Staff are waiting
# on the screen, so it stays short. Bounds the POST only: a token refresh on
# Cloud Run asks the metadata server with its own timeout and retries.
APPEND_TIMEOUT_S = 10

@cache
def _session() -> AuthorizedSession:
    """Built on first use, never at import: building it looks up credentials."""
    credentials, _ = google.auth.default(
        scopes=["https://www.googleapis.com/auth/spreadsheets"]
    )
    return AuthorizedSession(credentials, max_refresh_attempts=0)


def add_to_sheet(final_value: str) -> None:
    session = _session()
    sheet_tab_id = int(os.environ["SHEET_TAB_ID"])
    url = f"https://sheets.googleapis.com/v4/spreadsheets/{os.environ['SHEET_ID']}:batchUpdate"
    body = {
        "requests": [
            {
                "appendCells": {
                    "sheetId": sheet_tab_id,
                    "rows": [
                        {
                            "values": [
                                {},
                                {"userEnteredValue": {"stringValue": final_value}},  
                            ]
                        }
                    ],
                    "fields": "userEnteredValue",
                }
            }
        ]
    }
    response = session.post(url, json=body, timeout=APPEND_TIMEOUT_S)
    response.raise_for_status()
    