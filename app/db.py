"""The trial's Postgres.

Query functions take a connection, so the real-Postgres tests can pass their
own. The table is `deploy/schema.sql`.
"""

import os
from datetime import datetime
from functools import cache
from typing import Literal, LiteralString
from uuid import UUID

import psycopg
from google.cloud.sql.connector import Connector
from psycopg.types.json import Jsonb

# Covers the connector's certificate refresh and psycopg's connect: the first
# connect after a cold start makes two Admin API calls, then the handshake.
CONNECT_TIMEOUT_S = 15
# Every statement reads or writes one row by its key: one still running after
# this is hung, and should fail the request rather than hold the instance.
STATEMENT_TIMEOUT_MS = 5_000

INSERT_ITEM = """
    INSERT INTO items (id, received_at, revision, reading, value_shown)
    VALUES (%s, %s, %s, %s, %s)
"""


def _same_as(column: LiteralString) -> LiteralString:
    """ADR-0008, D5's comparison: the final value parameter against a stored
    column, after trimming spaces and uppercasing both; leading zeros count.
    Against the parameter, never the final_value column: in an UPDATE's SET,
    that column still holds its old value."""
    return f"upper(btrim(%(final_value)s)) = upper(btrim({column}))"


# D7 step 1 (as amended 2026-11-19): only an unconfirmed item with a value
# shown. The value_shown guard makes an empty read a miss here, rather than a
# CHECK violation.
CONFIRM_ITEM = f"""
    UPDATE items
    SET final_value = %(final_value)s,
        outcome = CASE WHEN {_same_as("value_shown")} THEN 'unchanged' ELSE 'edited' END,
        confirmed_at = %(confirmed_at)s
    WHERE id = %(id)s AND confirmed_at IS NULL AND value_shown IS NOT NULL
"""

# Why CONFIRM_ITEM matched no row.
CLASSIFY_MISS = f"""
    SELECT value_shown IS NULL, {_same_as("final_value")}
    FROM items WHERE id = %(id)s
"""

ConfirmResult = Literal["confirmed", "repeated", "conflict", "empty_read", "not_found"]


@cache
def _connector() -> Connector:
    """Built on first use, never at import: it starts a background thread, and
    the image must start with no configuration."""
    return Connector(refresh_strategy="lazy", timeout=CONNECT_TIMEOUT_S)


def connect() -> psycopg.Connection:
    """One connection per request, as the runtime database user, by IAM.

    Autocommit: each request makes one write. A confirm's SELECT after it
    only explains a miss, and needs no transaction: the app never undoes a
    confirm or changes a value shown. The real-Postgres tests' connection
    is autocommit too, so what they pass is what production does. The
    caller closes it.
    """
    return _connector().connect(
        os.environ["CLOUD_SQL_INSTANCE"],
        "psycopg",
        user=os.environ["DB_USER"],
        db=os.environ["DB_NAME"],
        enable_iam_auth=True,
        autocommit=True,
        options=f"-c statement_timeout={STATEMENT_TIMEOUT_MS}",
    )


def insert_item(
    conn: psycopg.Connection,
    *,
    item_id: UUID,
    received_at: datetime,
    revision: str | None,
    reading: dict,
    value_shown: str | None,
) -> None:
    """Store one read. The confirm columns stay NULL until a confirm."""
    conn.execute(INSERT_ITEM, (item_id, received_at, revision, Jsonb(reading), value_shown))


def confirm_item(
    conn: psycopg.Connection, *, item_id: UUID, final_value: str, confirmed_at: datetime
) -> ConfirmResult:
    """Confirm one item, storing final_value as entered (ADR-0008, D5, D7).

    `confirmed` when this call confirmed it. Otherwise the row is unchanged:
    `repeated` if it was already confirmed with the same final value (D5's
    comparison), `conflict` if with a different one, `empty_read` if its
    value shown is empty, `not_found` if there is no such item.
    """
    params = {"id": item_id, "final_value": final_value, "confirmed_at": confirmed_at}
    if conn.execute(CONFIRM_ITEM, params).rowcount == 1:
        return "confirmed"
    row = conn.execute(CLASSIFY_MISS, params).fetchone()
    if row is None:
        return "not_found"
    empty_read, same = row
    if empty_read:
        return "empty_read"
    return "repeated" if same else "conflict"
