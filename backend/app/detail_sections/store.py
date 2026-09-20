from __future__ import annotations

from datetime import datetime, timezone

from app.db.connection import get_connection

SECTION_KEYS = [
    "details",
    "description_features",
    "nearest_stations",
    "floorplans",
    "epc",
    "room_sizes",
    "commute",
    "frequent_destinations",
    "mortgage",
    "crime",
    "jobs",
    "local_politics",
]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_row(row) -> dict:
    return {f"{key}_expanded": bool(row[f"{key}_expanded"]) for key in SECTION_KEYS}


def get_config() -> dict:
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM detail_page_sections_config WHERE id = 1").fetchone()
        return _load_row(row)
    finally:
        conn.close()


def put_config(values: dict) -> dict:
    conn = get_connection()
    try:
        columns = [f"{key}_expanded" for key in SECTION_KEYS]
        assignments = ", ".join(f"{col} = ?" for col in columns)
        params = [int(bool(values[col])) for col in columns]
        conn.execute(
            f"UPDATE detail_page_sections_config SET {assignments}, updated_at = ? WHERE id = 1",
            (*params, _now_iso()),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM detail_page_sections_config WHERE id = 1").fetchone()
        return _load_row(row)
    finally:
        conn.close()
