"""Hand-rolled migration runner: schema_version table + ordered .sql files.

Each migration file is named NNNN_description.sql. On startup we compare the
highest applied version against the files on disk and run whatever's missing,
in order, inside a single transaction per file.
"""
import os
import re
import sqlite3

from app.db.connection import get_connection

MIGRATIONS_DIR = os.path.join(os.path.dirname(__file__), "migrations")
FILENAME_RE = re.compile(r"^(\d{4})_.*\.sql$")


def _migration_files():
    files = []
    for name in os.listdir(MIGRATIONS_DIR):
        match = FILENAME_RE.match(name)
        if match:
            files.append((int(match.group(1)), name))
    return sorted(files)


def run_migrations(conn: sqlite3.Connection | None = None) -> None:
    owns_conn = conn is None
    conn = conn or get_connection()
    try:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_version (version INTEGER PRIMARY KEY)"
        )
        row = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()
        current_version = row[0] or 0

        for version, filename in _migration_files():
            if version <= current_version:
                continue
            path = os.path.join(MIGRATIONS_DIR, filename)
            with open(path) as f:
                sql = f.read()
            conn.executescript(sql)
            conn.execute("INSERT INTO schema_version (version) VALUES (?)", (version,))
            conn.commit()
            print(f"Applied migration {filename}")
    finally:
        if owns_conn:
            conn.close()


if __name__ == "__main__":
    run_migrations()
