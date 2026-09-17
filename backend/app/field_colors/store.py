from __future__ import annotations

from datetime import datetime, timezone

from app.db.connection import get_connection
from app.field_colors.fields import EPC_BANDS, field_kind


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _validate(field: str, green_cutoff, red_cutoff, higher_is_better):
    """Validates a field+cutoffs+direction combination and returns the
    normalized (green_cutoff, red_cutoff, higher_is_better) tuple to store.
    Either cutoff may be None ("no rule on that side"), but the field and
    (for numeric fields) direction must always be valid."""
    kind = field_kind(field)
    if kind is None:
        raise ValueError(f"unknown field-color field: {field}")

    if kind == "epc_band":
        if higher_is_better is not None:
            raise ValueError("epc_current has a fixed band order; higher_is_better is not applicable")
        normalized = []
        for value in (green_cutoff, red_cutoff):
            if value is None:
                normalized.append(None)
                continue
            band = str(value).strip().upper()
            if band not in EPC_BANDS:
                raise ValueError(f"value {value!r} is not an EPC band (expected one of {EPC_BANDS})")
            normalized.append(band)
        return normalized[0], normalized[1], None

    if higher_is_better is None:
        raise ValueError(f"higher_is_better is required for numeric field {field!r}")
    normalized = []
    for value in (green_cutoff, red_cutoff):
        if value is None:
            normalized.append(None)
            continue
        try:
            float(value)
        except (TypeError, ValueError):
            raise ValueError(f"value {value!r} is not numeric")
        normalized.append(str(value))
    return normalized[0], normalized[1], bool(higher_is_better)


def list_thresholds() -> list[dict]:
    conn = get_connection()
    try:
        rows = conn.execute("SELECT * FROM field_color_thresholds ORDER BY field ASC").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def upsert_threshold(field: str, green_cutoff, red_cutoff, higher_is_better) -> dict:
    """One row per field, keyed by the field name itself -- the admin panel
    always edits a fixed, known field set, so create-or-replace is simpler
    than standards_rules' separate create/patch split (same precedent as
    council_tax_rates.upsert_rates, also keyed by a natural key)."""
    green, red, higher = _validate(field, green_cutoff, red_cutoff, higher_is_better)
    conn = get_connection()
    try:
        now = _now_iso()
        conn.execute(
            """
            INSERT INTO field_color_thresholds (field, green_cutoff, red_cutoff, higher_is_better, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(field) DO UPDATE SET
                green_cutoff = excluded.green_cutoff,
                red_cutoff = excluded.red_cutoff,
                higher_is_better = excluded.higher_is_better,
                updated_at = excluded.updated_at
            """,
            (field, green, red, None if higher is None else int(higher), now),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM field_color_thresholds WHERE field = ?", (field,)).fetchone()
        return dict(row)
    finally:
        conn.close()


def delete_threshold(field: str) -> None:
    conn = get_connection()
    try:
        conn.execute("DELETE FROM field_color_thresholds WHERE field = ?", (field,))
        conn.commit()
    finally:
        conn.close()
