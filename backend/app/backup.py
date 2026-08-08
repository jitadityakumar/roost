"""Simple periodic backup: a consistent copy of the SQLite DB (via sqlite3's
built-in backup API, safe to run against a live WAL-mode database) plus the
media directory, to a second location. Not sophisticated — just needs to
exist per the Phase 1 plan. Run manually or via cron:

    python3 -m app.backup
"""
import os
import shutil
import sqlite3
import sys
from datetime import datetime, timezone

from app.config import BASE_DATA_DIR, MEDIA_DIR
from app.db.connection import get_db_path

BACKUP_DIR = os.environ.get("ROOST_BACKUP_DIR", os.path.join(BASE_DATA_DIR, "..", "backups"))
KEEP_LAST_N = 7


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def backup_db(dest_path: str) -> None:
    db_path = get_db_path()
    if not os.path.exists(db_path):
        print(f"No database at {db_path}, skipping DB backup", file=sys.stderr)
        return
    source = sqlite3.connect(db_path)
    dest = sqlite3.connect(dest_path)
    try:
        source.backup(dest)
    finally:
        source.close()
        dest.close()


def backup_media(dest_dir: str) -> None:
    if not os.path.isdir(MEDIA_DIR):
        print(f"No media directory at {MEDIA_DIR}, skipping media backup", file=sys.stderr)
        return
    shutil.copytree(MEDIA_DIR, dest_dir, dirs_exist_ok=True)


def prune_old_backups() -> None:
    if not os.path.isdir(BACKUP_DIR):
        return
    entries = sorted(
        (e for e in os.listdir(BACKUP_DIR) if e.startswith("backup-")),
        reverse=True,
    )
    for stale in entries[KEEP_LAST_N:]:
        shutil.rmtree(os.path.join(BACKUP_DIR, stale), ignore_errors=True)


def run_backup() -> str:
    snapshot_dir = os.path.join(BACKUP_DIR, f"backup-{_timestamp()}")
    os.makedirs(snapshot_dir, exist_ok=True)

    backup_db(os.path.join(snapshot_dir, "roost.db"))
    backup_media(os.path.join(snapshot_dir, "media"))
    prune_old_backups()

    print(f"Backup written to {snapshot_dir}")
    return snapshot_dir


if __name__ == "__main__":
    run_backup()
