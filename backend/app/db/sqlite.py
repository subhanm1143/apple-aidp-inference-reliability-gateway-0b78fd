"""Thin SQLite connection helper. Repositories use `conn()`; nothing else in
the app touches raw SQL. Row factory gives dict-like rows so callers read by
name, the same discipline the rest of this project's repos rely on."""
from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from typing import Iterator

DB_PATH = os.environ.get("GATEWAY_DB", "gateway.db")


@contextmanager
def conn() -> Iterator[sqlite3.Connection]:
    """Borrow a connection, yield it, commit on success, always close."""
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys = ON")
    try:
        yield c
        c.commit()
    finally:
        c.close()


def init_schema() -> None:
    here = os.path.dirname(__file__)
    sql_path = os.path.join(here, "..", "models", "schema.sql")
    with open(sql_path, "r", encoding="utf-8") as fh:
        ddl = fh.read()
    with conn() as c:
        c.executescript(ddl)
