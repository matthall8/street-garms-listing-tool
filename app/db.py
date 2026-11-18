"""The trial's Postgres.

Query functions take a connection, so the real-Postgres tests can pass their
own. The table is `deploy/schema.sql`.
"""

import os
from datetime import datetime
from functools import cache
from uuid import UUID

import psycopg
from google.cloud.sql.connector import Connector
from psycopg.types.json import Jsonb

# Covers the connector's certificate refresh and psycopg's connect: the first
# connect after a cold start makes two Admin API calls, then the handshake.
CONNECT_TIMEOUT_S = 15
# One single-row INSERT per request: a statement still running after this is
# hung, and should fail the read rather than hold the instance.
STATEMENT_TIMEOUT_MS = 5_000

INSERT_ITEM = """
    INSERT INTO items (id, received_at, revision, reading, value_shown)
    VALUES (%s, %s, %s, %s, %s)
"""


@cache
def _connector() -> Connector:
    """Built on first use, never at import: it starts a background thread, and
    the image must start with no configuration."""
    return Connector(refresh_strategy="lazy", timeout=CONNECT_TIMEOUT_S)


def connect() -> psycopg.Connection:
    """One connection per request, as the runtime database user, by IAM.

    Autocommit: each request runs one statement, and the real-Postgres tests'
    connection is autocommit too, so what they pass is what production does.
    The caller closes it.
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
    """Store one read. The confirm and Sheet columns stay NULL until a confirm."""
    conn.execute(INSERT_ITEM, (item_id, received_at, revision, Jsonb(reading), value_shown))
