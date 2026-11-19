"""app/sheet.py, with the credentials and the session mocked. That no
credentials are built at import is checked in tests/test_db.py, with the
other clients."""

from types import SimpleNamespace
from unittest import mock

import pytest
import requests

from app import sheet
from tests import synthetic as s

SHEET_ID = "zz-sheet-id"
TAB_ID = 12345
LEADING_ZERO = "0" + s.SPLIT_SI_9


def _response(status: int) -> requests.Response:
    """A real Response, so raise_for_status() runs rather than a mock of it."""
    response = requests.Response()
    response.status_code = status
    response.url = "https://sheets.invalid/"
    return response


@pytest.fixture
def session(monkeypatch):
    monkeypatch.setenv("SHEET_ID", SHEET_ID)
    monkeypatch.setenv("SHEET_TAB_ID", str(TAB_ID))
    sheet._session.cache_clear()
    credentials = mock.sentinel.credentials
    with (
        mock.patch.object(sheet.google.auth, "default", return_value=(credentials, None)) as default,
        mock.patch.object(sheet, "AuthorizedSession") as cls,
    ):
        cls.return_value.post.return_value = _response(200)
        yield SimpleNamespace(default=default, cls=cls, post=cls.return_value.post)
    sheet._session.cache_clear()


def test_append_sends_one_appendcells_on_the_tab(session):
    sheet.add_to_sheet(LEADING_ZERO)

    session.post.assert_called_once()
    (url,), kwargs = session.post.call_args
    assert url == f"https://sheets.googleapis.com/v4/spreadsheets/{SHEET_ID}:batchUpdate"
    assert kwargs == {
        "json": {
            "requests": [
                {
                    "appendCells": {
                        "sheetId": TAB_ID,
                        "rows": [
                            {
                                "values": [
                                    {},
                                    {"userEnteredValue": {"stringValue": LEADING_ZERO}},
                                ]
                            }
                        ],
                        "fields": "userEnteredValue",
                    }
                }
            ]
        },
        "timeout": sheet.APPEND_TIMEOUT_S,
    }


def test_the_value_goes_as_a_string_with_its_leading_zero(session):
    sheet.add_to_sheet(LEADING_ZERO)

    cells = session.post.call_args.kwargs["json"]["requests"][0]["appendCells"]["rows"][0]["values"]
    assert cells[0] == {}, "column A is left for staff"
    value = cells[1]["userEnteredValue"]
    assert list(value) == ["stringValue"]
    assert value["stringValue"] == LEADING_ZERO
    assert value["stringValue"].startswith("0")


def test_the_session_has_the_sheets_scope_and_never_refreshes_and_resends(session):
    sheet.add_to_sheet(LEADING_ZERO)

    session.default.assert_called_once_with(
        scopes=["https://www.googleapis.com/auth/spreadsheets"]
    )
    session.cls.assert_called_once_with(mock.sentinel.credentials, max_refresh_attempts=0)


def test_the_session_is_built_once(session):
    sheet.add_to_sheet(LEADING_ZERO)
    sheet.add_to_sheet(LEADING_ZERO)

    session.default.assert_called_once()
    session.cls.assert_called_once()
    assert session.post.call_count == 2


@pytest.mark.parametrize("status", [400, 401, 403, 404, 429, 500, 503])
def test_a_non_2xx_response_raises(session, status):
    session.post.return_value = _response(status)

    with pytest.raises(requests.HTTPError):
        sheet.add_to_sheet(LEADING_ZERO)


def test_an_exception_from_the_session_raises(session):
    session.post.side_effect = requests.Timeout()

    with pytest.raises(requests.Timeout):
        sheet.add_to_sheet(LEADING_ZERO)
    session.post.assert_called_once()


@pytest.mark.parametrize("name", ["SHEET_ID", "SHEET_TAB_ID"])
def test_missing_configuration_raises_and_sends_nothing(session, monkeypatch, name):
    monkeypatch.delenv(name)

    with pytest.raises(KeyError):
        sheet.add_to_sheet(LEADING_ZERO)
    session.post.assert_not_called()


def test_a_tab_id_that_is_not_a_number_raises_and_sends_nothing(session, monkeypatch):
    monkeypatch.setenv("SHEET_TAB_ID", "intake")

    with pytest.raises(ValueError):
        sheet.add_to_sheet(LEADING_ZERO)
    session.post.assert_not_called()
