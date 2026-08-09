from __future__ import annotations

import json
import re
from datetime import datetime, timezone

from app.db.connection import get_connection

MAX_BASELINES = 3


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_postcode(postcode: str) -> str:
    return re.sub(r"\s+", "", postcode.strip().upper())


def list_baselines() -> list[dict]:
    conn = get_connection()
    try:
        rows = conn.execute("SELECT * FROM crime_baselines ORDER BY created_at ASC").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def create_baseline(label: str, postcode: str) -> dict:
    conn = get_connection()
    try:
        count = conn.execute("SELECT COUNT(*) FROM crime_baselines").fetchone()[0]
        if count >= MAX_BASELINES:
            raise ValueError(f"only {MAX_BASELINES} baselines are allowed")
        now = _now_iso()
        cur = conn.execute(
            "INSERT INTO crime_baselines (label, postcode, created_at) VALUES (?, ?, ?)",
            (label, postcode, now),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM crime_baselines WHERE id = ?", (cur.lastrowid,)).fetchone()
        return dict(row)
    finally:
        conn.close()


def delete_baseline(baseline_id: int) -> None:
    conn = get_connection()
    try:
        conn.execute("DELETE FROM crime_baselines WHERE id = ?", (baseline_id,))
        conn.commit()
    finally:
        conn.close()


def get_cached_stats(postcode: str) -> dict | None:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM crime_stats_cache WHERE postcode = ?", (normalize_postcode(postcode),)
        ).fetchone()
        if row is None:
            return None
        out = dict(row)
        out["category_counts"] = json.loads(out["category_counts"])
        return out
    finally:
        conn.close()


def save_stats(postcode: str, lat: float, lng: float, category_counts: dict[str, int]) -> dict:
    conn = get_connection()
    try:
        normalized = normalize_postcode(postcode)
        now = _now_iso()
        conn.execute(
            """
            INSERT INTO crime_stats_cache (postcode, lat, lng, category_counts, fetched_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(postcode) DO UPDATE SET
                lat = excluded.lat, lng = excluded.lng,
                category_counts = excluded.category_counts, fetched_at = excluded.fetched_at
            """,
            (normalized, lat, lng, json.dumps(category_counts), now),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM crime_stats_cache WHERE postcode = ?", (normalized,)).fetchone()
        out = dict(row)
        out["category_counts"] = json.loads(out["category_counts"])
        return out
    finally:
        conn.close()
