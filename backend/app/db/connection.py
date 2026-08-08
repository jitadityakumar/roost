import os
import sqlite3
from contextlib import contextmanager

from app.config import BASE_DATA_DIR


def _configure(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA foreign_keys=ON")


def get_db_path() -> str:
    # Read fresh (rather than freezing at import time) so tests can point
    # this at a per-test temp file via the env var without caring about
    # import order.
    return os.environ.get("ROOST_DB_PATH", os.path.join(BASE_DATA_DIR, "roost.db"))


def get_connection() -> sqlite3.Connection:
    db_path = get_db_path()
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    _configure(conn)
    return conn


@contextmanager
def db_cursor():
    conn = get_connection()
    try:
        cur = conn.cursor()
        yield cur
        conn.commit()
    finally:
        conn.close()
