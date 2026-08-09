from __future__ import annotations

from datetime import datetime, timezone

from app.db.connection import get_connection
from app.standards.fields import EPC_BANDS, field_type, is_valid_operator


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _validate(field: str, operator: str, value: str) -> str:
    """Validates the field+operator+value combination and returns the value
    normalized for storage (e.g. an epc_band letter uppercased)."""
    kind = field_type(field)
    if kind is None:
        raise ValueError(f"unknown standards field: {field}")
    if not is_valid_operator(field, operator):
        raise ValueError(f"operator {operator!r} not valid for field {field!r}")
    if kind == "numeric":
        try:
            float(value)
        except (TypeError, ValueError):
            raise ValueError(f"value {value!r} is not numeric")
        return str(value)
    if kind == "epc_band":
        normalized = str(value).strip().upper()
        if normalized not in EPC_BANDS:
            raise ValueError(f"value {value!r} is not an EPC band (expected one of {EPC_BANDS})")
        return normalized
    if str(value).lower() not in ("true", "false", "0", "1"):
        raise ValueError(f"value {value!r} is not a boolean")
    return str(value)


def list_rules() -> list[dict]:
    conn = get_connection()
    try:
        rows = conn.execute("SELECT * FROM standards_rules ORDER BY created_at ASC").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def create_rule(field: str, operator: str, value: str) -> dict:
    normalized_value = _validate(field, operator, value)
    conn = get_connection()
    try:
        now = _now_iso()
        cur = conn.execute(
            "INSERT INTO standards_rules (field, operator, value, enabled, created_at) VALUES (?, ?, ?, 1, ?)",
            (field, operator, normalized_value, now),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM standards_rules WHERE id = ?", (cur.lastrowid,)).fetchone()
        return dict(row)
    finally:
        conn.close()


def update_rule(rule_id: int, **changes) -> dict | None:
    """Partial update: any of field/operator/value/enabled. Validates the
    resulting field+operator+value combination against the *merged* row (an
    update might only touch one of the three), not just the changed keys."""
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM standards_rules WHERE id = ?", (rule_id,)).fetchone()
        if row is None:
            return None
        merged = dict(row)
        merged.update({k: v for k, v in changes.items() if v is not None})

        to_write = {k: merged[k] for k in ("field", "operator", "value", "enabled")}
        if any(k in changes for k in ("field", "operator", "value")):
            to_write["value"] = _validate(merged["field"], merged["operator"], str(merged["value"]))
        else:
            to_write["value"] = str(to_write["value"])
        set_clause = ", ".join(f"{k} = ?" for k in to_write)
        conn.execute(
            f"UPDATE standards_rules SET {set_clause} WHERE id = ?",
            (*to_write.values(), rule_id),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM standards_rules WHERE id = ?", (rule_id,)).fetchone()
        return dict(row)
    finally:
        conn.close()


def delete_rule(rule_id: int) -> None:
    conn = get_connection()
    try:
        conn.execute("DELETE FROM standards_rules WHERE id = ?", (rule_id,))
        conn.commit()
    finally:
        conn.close()
