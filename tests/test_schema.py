from datetime import UTC, datetime
from uuid import UUID, uuid4

import psycopg
import pytest
from psycopg import sql
from psycopg.types.json import Jsonb

from labels.schemas import ArtNumberReading
from tests import synthetic as s

CLEAN_READING = ArtNumberReading(art_number_raw=s.SPLIT_SI_9, art_legible="clear").model_dump()
EMPTY_READING = ArtNumberReading(art_number_raw=None, art_legible="not_visible").model_dump()
SELECT_STORED = "SELECT value_shown, reading FROM items WHERE id = %s"

NOW = datetime.now(UTC)
CONFIRMED_SENT = {
    "final_value": s.SPLIT_SI_8,
    "outcome": "edited",
    "confirmed_at": NOW,
    "sheet_status": "sent",
    "sheet_updated_at": NOW,
}


def _insert(conn: psycopg.Connection, **columns: object) -> UUID:
    """Insert one items row, a clean read unless keyword arguments override
    or add columns. Returns its id."""
    item_id = uuid4()
    row = {
        "id": item_id,
        "received_at": datetime.now(UTC),
        "reading": CLEAN_READING,
        "value_shown": s.SPLIT_SI_9,
        **columns,
    }
    row["reading"] = Jsonb(row["reading"])
    query = sql.SQL("INSERT INTO items ({}) VALUES ({})").format(
        sql.SQL(", ").join(map(sql.Identifier, row)),
        sql.SQL(", ").join([sql.Placeholder()] * len(row)),
    )
    conn.execute(query, tuple(row.values()))
    return item_id


def test_a_row_stores(pg_conn: psycopg.Connection):
    item_id = _insert(pg_conn)
    assert pg_conn.execute(SELECT_STORED, (item_id,)).fetchone() == (s.SPLIT_SI_9, CLEAN_READING)


def test_an_empty_read_stores(pg_conn: psycopg.Connection):
    item_id = _insert(pg_conn, reading=EMPTY_READING, value_shown=None)
    assert pg_conn.execute(SELECT_STORED, (item_id,)).fetchone() == (None, EMPTY_READING)


def test_a_confirmed_sent_row_stores(pg_conn: psycopg.Connection):
    item_id = _insert(pg_conn, **CONFIRMED_SENT)
    stored = pg_conn.execute(
        "SELECT final_value, outcome, confirmed_at, sheet_status, sheet_updated_at"
        " FROM items WHERE id = %s",
        (item_id,),
    ).fetchone()
    assert stored == tuple(CONFIRMED_SENT.values())


# Each row breaks exactly one rule in deploy/schema.sql and is otherwise valid,
# so a refusal can only come from the rule it names.
BAD_ROWS = [
    pytest.param({"value_shown": ""}, id="value_shown is the empty string"),
    pytest.param({**CONFIRMED_SENT, "outcome": None}, id="confirm without outcome"),
    pytest.param({**CONFIRMED_SENT, "final_value": None}, id="confirm without final_value"),
    pytest.param({"final_value": s.SPLIT_SI_8, "outcome": "edited"}, id="confirm without confirmed_at"),
    pytest.param(
        {**CONFIRMED_SENT, "reading": EMPTY_READING, "value_shown": None},
        id="confirm on an empty read",
    ),
    pytest.param({"sheet_status": "pending", "sheet_updated_at": NOW}, id="Sheet state without a confirm"),
    pytest.param(
        {**CONFIRMED_SENT, "sheet_status": None, "sheet_updated_at": None},
        id="confirm without Sheet state",
    ),
    pytest.param({**CONFIRMED_SENT, "outcome": "approved"}, id="outcome outside its list"),
    pytest.param({**CONFIRMED_SENT, "sheet_status": "queued"}, id="sheet_status outside its list"),
]


@pytest.mark.parametrize("columns", BAD_ROWS)
def test_the_schema_refuses_a_bad_row(pg_conn: psycopg.Connection, columns: dict):
    with pytest.raises(psycopg.errors.CheckViolation):
        _insert(pg_conn, **columns)
    assert pg_conn.execute("SELECT count(*) FROM items").fetchone() == (0,)
