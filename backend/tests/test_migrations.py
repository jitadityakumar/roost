import os
import shutil
import sqlite3

import pytest

from app.db import migrate


def test_migration_0040_adds_offer_status_and_comment_type(tmp_path, monkeypatch):
    src = migrate.MIGRATIONS_DIR
    old_dir = tmp_path / "old"
    old_dir.mkdir()
    for _, name in migrate._migration_files():
        if int(name[:4]) < 40:
            shutil.copy(os.path.join(src, name), old_dir / name)

    db = str(tmp_path / "upgrade.db")
    monkeypatch.setenv("ROOST_DB_PATH", db)
    monkeypatch.setattr(migrate, "MIGRATIONS_DIR", str(old_dir))
    migrate.run_migrations()

    conn = sqlite3.connect(db)
    now = "2026-01-01T00:00:00"
    statuses = ["triage", "parked", "approved", "rejected", "viewing", "contacted"]
    for i, status in enumerate(statuses, start=1):
        conn.execute(
            "INSERT INTO listings (id, url, user_status, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            (i, f"u{i}", status, now, now),
        )
    conn.execute(
        "INSERT INTO comments (listing_id, comment_type, text, initials, created_at, updated_at) "
        "VALUES (4, 'rejection', 'too small', 'JK', ?, ?)",
        (now, now),
    )
    conn.commit()
    conn.close()

    monkeypatch.setattr(migrate, "MIGRATIONS_DIR", src)
    migrate.run_migrations()

    conn = sqlite3.connect(db)
    assert conn.execute("SELECT id, user_status FROM listings ORDER BY id").fetchall() == list(
        enumerate(statuses, start=1)
    )
    assert conn.execute("SELECT text FROM comments").fetchall() == [("too small",)]
    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    assert conn.execute("SELECT name FROM sqlite_master WHERE name='idx_comments_listing_id'").fetchone()

    conn.execute("UPDATE listings SET user_status = 'offer' WHERE id = 1")
    conn.execute(
        "INSERT INTO comments (listing_id, comment_type, text, initials, created_at, updated_at) "
        "VALUES (1, 'offer', 'offered', 'JK', ?, ?)",
        (now, now),
    )
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("UPDATE listings SET user_status = 'bogus' WHERE id = 1")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO comments (listing_id, comment_type, text, created_at, updated_at) "
            "VALUES (1, 'bogus', 'x', ?, ?)",
            (now, now),
        )
    conn.close()


def test_migration_0039_adds_parked_and_preserves_data(tmp_path, monkeypatch):
    src = migrate.MIGRATIONS_DIR
    old_dir = tmp_path / "old"
    old_dir.mkdir()
    for _, name in migrate._migration_files():
        if int(name[:4]) < 39:
            shutil.copy(os.path.join(src, name), old_dir / name)

    db = str(tmp_path / "upgrade.db")
    monkeypatch.setenv("ROOST_DB_PATH", db)
    monkeypatch.setattr(migrate, "MIGRATIONS_DIR", str(old_dir))
    migrate.run_migrations()

    conn = sqlite3.connect(db)
    now = "2026-01-01T00:00:00"
    statuses = ["triage", "approved", "rejected", "viewing", "contacted"]
    for i, status in enumerate(statuses, start=1):
        conn.execute(
            "INSERT INTO listings (id, url, user_status, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            (i, f"u{i}", status, now, now),
        )
    conn.execute(
        "INSERT INTO comments (listing_id, comment_type, text, initials, created_at, updated_at) "
        "VALUES (3, 'rejection', 'too small', 'JK', ?, ?)",
        (now, now),
    )
    conn.execute(
        "INSERT INTO jobs (listing_id, job_type, lane, status, created_at, updated_at) "
        "VALUES (1, 'rightmove_extract', 'http', 'done', ?, ?)",
        (now, now),
    )
    conn.commit()
    conn.close()

    monkeypatch.setattr(migrate, "MIGRATIONS_DIR", src)
    migrate.run_migrations()

    conn = sqlite3.connect(db)
    assert conn.execute("SELECT id, user_status FROM listings ORDER BY id").fetchall() == list(
        enumerate(statuses, start=1)
    )
    assert conn.execute("SELECT text FROM comments").fetchall() == [("too small",)]
    assert conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0] == 1
    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] in (0, 1)

    conn.execute("UPDATE listings SET user_status = 'parked' WHERE id = 1")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("UPDATE listings SET user_status = 'bogus' WHERE id = 1")
    conn.close()
