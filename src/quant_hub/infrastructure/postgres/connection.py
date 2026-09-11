from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import psycopg
from psycopg_pool import ConnectionPool

from quant_hub.config import database_url

_pool: ConnectionPool | None = None


def get_connection_url() -> str:
    return database_url()


def _get_pool() -> ConnectionPool:
    """Process-wide connection pool, created lazily on first use.

    A module-level singleton so every repository call (Streamlit reruns,
    CLI jobs within one process) shares a small set of live connections
    instead of dialing Postgres fresh per call.
    """
    global _pool
    if _pool is None:
        _pool = ConnectionPool(get_connection_url(), min_size=1, max_size=10, open=True)
    return _pool


@contextmanager
def get_connection(*, autocommit: bool = False) -> Iterator[psycopg.Connection]:
    with _get_pool().connection() as conn:
        if conn.autocommit != autocommit:
            conn.autocommit = autocommit
        try:
            yield conn
        finally:
            # Autocommit can't be changed while a transaction is open, so a
            # plain read (no explicit commit()) must be rolled back first —
            # this also leaves the connection clean for the next borrower.
            if conn.autocommit:
                conn.autocommit = False
            else:
                conn.rollback()


def ping() -> bool:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
            return cur.fetchone() is not None


def apply_schema(schema_path: Path | None = None) -> None:
    path = schema_path or Path(__file__).with_name("schema.sql")
    sql = path.read_text()
    with get_connection(autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
