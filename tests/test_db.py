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
        " confirmed_at, sheet_status, sheet_updated_at FROM items WHERE id = %s",
        (item_id,),
    ).fetchone()
    assert stored == (received_at, revision, READING, s.SPLIT_SI_9, None, None, None, None, None)


def test_import_and_create_app_build_no_client():
    """Decision 10: the CI docker job starts the image with no configuration.
    A fresh interpreter, because this process has imported app already."""
    code = (
        "from unittest import mock\n"
        "import google.cloud.sql.connector as c, google.cloud.storage as s\n"
        "built = AssertionError('a client was built at import or in create_app()')\n"
        "with mock.patch.object(c, 'Connector', side_effect=built),"
        " mock.patch.object(s, 'Client', side_effect=built):\n"
        "    import app, app.db\n"
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
