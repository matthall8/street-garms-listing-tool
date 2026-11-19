"""app/db.py: the insert against real Postgres, and how the connector is built
and connects, with the connector mocked."""

import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from unittest import mock
from uuid import uuid4

import psycopg
import pytest

from app import db
from labels.schemas import ArtNumberReading
from tests import synthetic as s

ROOT = Path(__file__).resolve().parent.parent
READING = ArtNumberReading(art_number_raw=s.SPLIT_SI_9, art_legible="clear").model_dump()


@pytest.mark.parametrize("revision", ["listing-tool-00007-zzz", None], ids=["on Cloud Run", "off Cloud Run"])
def test_insert_item_stores_the_read(pg_conn: psycopg.Connection, revision):
    item_id, received_at = uuid4(), datetime.now(UTC)
    db.insert_item(
        pg_conn,
        item_id=item_id,
        received_at=received_at,
        revision=revision,
        reading=READING,
        value_shown=s.SPLIT_SI_9,
    )
    stored = pg_conn.execute(
        "SELECT received_at, revision, reading, value_shown, final_value, outcome,"
        " confirmed_at FROM items WHERE id = %s",
        (item_id,),
    ).fetchone()
    assert stored == (received_at, revision, READING, s.SPLIT_SI_9, None, None, None)


def test_import_and_create_app_build_no_client():
    """Decision 10: the CI docker job starts the image with no configuration.
    A fresh interpreter, because this process has imported app already."""
    code = (
        "from unittest import mock\n"
        "import google.cloud.sql.connector as c, google.cloud.storage as s\n"
        "import google.auth as a, google.auth.transport.requests as r\n"
        "built = AssertionError('a client was built at import or in create_app()')\n"
        "with mock.patch.object(c, 'Connector', side_effect=built),"
        " mock.patch.object(s, 'Client', side_effect=built),"
        " mock.patch.object(a, 'default', side_effect=built),"
        " mock.patch.object(r, 'AuthorizedSession', side_effect=built):\n"
        "    import app, app.db, app.photos, app.sheet\n"
        "    app.create_app()\n"
    )
    result = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


@pytest.fixture
def connector(monkeypatch):
    monkeypatch.setenv("CLOUD_SQL_INSTANCE", "zz-project:zz-region:zz-pg")
    monkeypatch.setenv("DB_USER", "zz-runtime@zz-project.iam")
    monkeypatch.setenv("DB_NAME", "zz_db")
    db._connector.cache_clear()
    with mock.patch.object(db, "Connector") as cls:
        yield cls
    db._connector.cache_clear()


def test_connect_is_lazy_iam_autocommit_with_timeouts(connector):
    conn = db.connect()
    db.connect()

    connector.assert_called_once_with(refresh_strategy="lazy", timeout=db.CONNECT_TIMEOUT_S)
    assert conn is connector.return_value.connect.return_value
    connector.return_value.connect.assert_called_with(
        "zz-project:zz-region:zz-pg",
        "psycopg",
        user="zz-runtime@zz-project.iam",
        db="zz_db",
        enable_iam_auth=True,
        autocommit=True,
        options=f"-c statement_timeout={db.STATEMENT_TIMEOUT_MS}",
    )


# The confirm, against real Postgres (ADR-0008, D5, D7, D8).

SELECT_CONFIRM = "SELECT final_value, outcome, confirmed_at FROM items WHERE id = %s"


def _item(conn: psycopg.Connection, value_shown: str | None = s.SPLIT_SI_9):
    """Insert an unconfirmed item; value_shown=None is an empty read."""
    item_id = uuid4()
    reading = (
        READING
        if value_shown
        else ArtNumberReading(art_number_raw=None, art_legible="not_visible").model_dump()
    )
    db.insert_item(
        conn,
        item_id=item_id,
        received_at=datetime.now(UTC),
        revision=None,
        reading=reading,
        value_shown=value_shown,
    )
    return item_id


def _stored(conn: psycopg.Connection, item_id) -> tuple:
    row = conn.execute(SELECT_CONFIRM, (item_id,)).fetchone()
    assert row is not None
    return row


def _confirm(conn: psycopg.Connection, item_id, final_value: str):
    return db.confirm_item(
        conn, item_id=item_id, final_value=final_value, confirmed_at=datetime.now(UTC)
    )


@pytest.mark.parametrize(
    "final_value, outcome",
    [
        pytest.param(s.SPLIT_SI_9, "unchanged", id="as shown"),
        pytest.param(f"  {s.SPLIT_SI_9.lower()} ", "unchanged", id="spaces and case"),
        pytest.param(s.SPLIT_SI_8, "edited", id="different"),
        pytest.param("0" + s.SPLIT_SI_9, "edited", id="a leading zero added"),
        pytest.param(f"\t{s.SPLIT_SI_9}", "edited", id="a tab is not a space"),
    ],
)
def test_confirm_stores_the_value_as_entered_and_the_outcome(
    pg_conn: psycopg.Connection, final_value, outcome
):
    """D5: the outcome comes from the stored value shown, compared after
    trimming spaces and uppercasing; the final value is stored as entered.
    "as shown" also catches a comparison with the final_value column, which
    SET reads as NULL, making every confirm edited."""
    item_id = _item(pg_conn)
    before = datetime.now(UTC)
    assert _confirm(pg_conn, item_id, final_value) == "confirmed"
    stored_value, stored_outcome, confirmed_at = _stored(pg_conn, item_id)
    assert (stored_value, stored_outcome) == (final_value, outcome)
    assert confirmed_at >= before


@pytest.mark.parametrize(
    "second, result",
    [
        pytest.param(s.SPLIT_SI_8, "repeated", id="same value"),
        pytest.param(f" {s.SPLIT_SI_8.lower()}", "repeated", id="same under D5's comparison"),
        pytest.param(s.SPLIT_SI_9, "conflict", id="different value"),
    ],
)
def test_a_second_confirm_changes_nothing(pg_conn: psycopg.Connection, second, result):
    """D7, D8: the first confirm stands, whatever the second sends."""
    item_id = _item(pg_conn)
    assert _confirm(pg_conn, item_id, s.SPLIT_SI_8) == "confirmed"
    first = _stored(pg_conn, item_id)

    assert _confirm(pg_conn, item_id, second) == result
    assert _stored(pg_conn, item_id) == first


def test_a_confirm_on_an_empty_read_changes_nothing(pg_conn: psycopg.Connection):
    """D5: refused, and refused by the guard, not the schema's CHECK."""
    item_id = _item(pg_conn, value_shown=None)
    assert _confirm(pg_conn, item_id, s.SPLIT_SI_9) == "empty_read"
    assert _stored(pg_conn, item_id) == (None, None, None)


def test_a_confirm_on_an_unknown_id_changes_nothing(pg_conn: psycopg.Connection):
    item_id = _item(pg_conn)
    assert _confirm(pg_conn, uuid4(), s.SPLIT_SI_9) == "not_found"
    assert pg_conn.execute("SELECT count(*) FROM items").fetchone() == (1,)
    assert _stored(pg_conn, item_id) == (None, None, None)


# Post to Sheet's read, against real Postgres (ADR-0008, D7, as amended).


@pytest.mark.parametrize(
    "final_value",
    [
        pytest.param(s.SPLIT_SI_9, id="as shown"),
        pytest.param("0" + s.SPLIT_SI_9, id="edited, with a leading zero"),
    ],
)
def test_a_confirmed_item_gives_its_stored_final_value(pg_conn: psycopg.Connection, final_value):
    item_id = _item(pg_conn)
    assert _confirm(pg_conn, item_id, final_value) == "confirmed"
    assert db.confirmed_final_value(pg_conn, item_id=item_id) == ("confirmed", final_value)


@pytest.mark.parametrize("second", [s.SPLIT_SI_8, s.SPLIT_SI_9], ids=["repeated", "conflict"])
def test_the_value_is_the_first_confirm_s_after_a_second(pg_conn: psycopg.Connection, second):
    item_id = _item(pg_conn)
    assert _confirm(pg_conn, item_id, s.SPLIT_SI_8) == "confirmed"
    _confirm(pg_conn, item_id, second)
    assert db.confirmed_final_value(pg_conn, item_id=item_id) == ("confirmed", s.SPLIT_SI_8)


@pytest.mark.parametrize("value_shown", [s.SPLIT_SI_9, None], ids=["unconfirmed", "empty read"])
def test_an_unconfirmed_item_gives_no_value(pg_conn: psycopg.Connection, value_shown):
    item_id = _item(pg_conn, value_shown=value_shown)
    assert db.confirmed_final_value(pg_conn, item_id=item_id) == ("unconfirmed", None)


def test_an_unknown_id_gives_no_value(pg_conn: psycopg.Connection):
    item_id = _item(pg_conn)
    _confirm(pg_conn, item_id, s.SPLIT_SI_9)
    assert db.confirmed_final_value(pg_conn, item_id=uuid4()) == ("not_found", None)
    assert db.confirmed_final_value(pg_conn, item_id=item_id) == ("confirmed", s.SPLIT_SI_9)


def test_the_read_changes_nothing(pg_conn: psycopg.Connection):
    item_id = _item(pg_conn)
    _confirm(pg_conn, item_id, s.SPLIT_SI_8)
    before = _stored(pg_conn, item_id)
    db.confirmed_final_value(pg_conn, item_id=item_id)
    assert _stored(pg_conn, item_id) == before
