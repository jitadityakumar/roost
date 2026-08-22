"""Council tax rates: one row per council (council_tax_rates), keyed by GSS
code -- never joined by council_name, which is display-only (a council can
be renamed; GSS is stable). See app/crime/client.py::lookup_postcode for
how a listing's admin_district/admin_district_gss get populated in the
first place (issue #60)."""
from __future__ import annotations

from datetime import datetime, timezone

from app.db.connection import get_connection

BAND_LETTERS = "ABCDEFGH"
BAND_COLUMNS = [f"band_{letter.lower()}" for letter in BAND_LETTERS]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _council_dict(gss_code: str, listing_name: str | None, rate: dict | None) -> dict:
    out = {"gss_code": gss_code, "council_name": (rate["council_name"] if rate else None) or listing_name}
    for col in BAND_COLUMNS:
        out[col] = rate[col] if rate else None
    out["updated_at"] = rate["updated_at"] if rate else None
    return out


def list_councils() -> list[dict]:
    """Every council that either has a listing resolved to it or already has
    a rates row (or both) -- see _council_dict's COALESCE-style name
    fallback. A council with rates but no current listing still appears
    (rates rows are never auto-deleted); a council with a listing but no
    rates row yet shows every band as None (the "needs rates" case)."""
    conn = get_connection()
    try:
        listing_rows = conn.execute(
            "SELECT DISTINCT admin_district_gss AS gss, admin_district AS name "
            "FROM listings WHERE admin_district_gss IS NOT NULL"
        ).fetchall()
        rate_rows = conn.execute("SELECT * FROM council_tax_rates").fetchall()
        rates_by_gss = {r["gss_code"]: dict(r) for r in rate_rows}

        seen = set()
        result = []
        for row in listing_rows:
            gss = row["gss"]
            result.append(_council_dict(gss, row["name"], rates_by_gss.get(gss)))
            seen.add(gss)
        for gss, rate in rates_by_gss.items():
            if gss not in seen:
                result.append(_council_dict(gss, None, rate))

        result.sort(key=lambda c: c["council_name"] or "")
        return result
    finally:
        conn.close()


def upsert_rates(gss_code: str, council_name: str, bands: dict) -> dict:
    """Full replacement of a council's 8 band rates -- not a merge. The
    caller must send all 8 band keys (None for "not set"); this is the only
    way to deliberately clear a wrong rate back to unset."""
    conn = get_connection()
    try:
        now = _now_iso()
        existing = conn.execute(
            "SELECT created_at FROM council_tax_rates WHERE gss_code = ?", (gss_code,)
        ).fetchone()
        created_at = existing["created_at"] if existing else now
        values = [bands.get(col) for col in BAND_COLUMNS]
        conn.execute(
            f"""
            INSERT INTO council_tax_rates
                (gss_code, council_name, {", ".join(BAND_COLUMNS)}, created_at, updated_at)
            VALUES (?, ?, {", ".join("?" for _ in BAND_COLUMNS)}, ?, ?)
            ON CONFLICT(gss_code) DO UPDATE SET
                council_name = excluded.council_name,
                {", ".join(f"{col} = excluded.{col}" for col in BAND_COLUMNS)},
                updated_at = excluded.updated_at
            """,
            (gss_code, council_name, *values, created_at, now),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM council_tax_rates WHERE gss_code = ?", (gss_code,)).fetchone()
        return dict(row)
    finally:
        conn.close()


def delete_council(gss_code: str) -> None:
    conn = get_connection()
    try:
        conn.execute("DELETE FROM council_tax_rates WHERE gss_code = ?", (gss_code,))
        conn.commit()
    finally:
        conn.close()


def monthly_estimate(gss_code: str | None, band: str | None) -> int | None:
    """None for a missing gss, a missing/invalid band letter, or an unset
    rate for that band -- never raises. round(annual / 12), matching
    service_charge_pm's existing rounding.

    Case-insensitive ("d" normalizes to the same result as "D"), but a
    single valid letter is required exactly -- a naive `.strip().upper()
    [:1]` would truncate "Band D" down to "B" and silently return band B's
    rate for a garbage input; requiring len == 1 before the membership
    check rejects "Band D"/"TBC"/"" outright instead."""
    if not gss_code:
        return None
    letter = (band or "").strip().upper()
    if len(letter) != 1 or letter not in BAND_LETTERS:
        return None
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM council_tax_rates WHERE gss_code = ?", (gss_code,)
        ).fetchone()
        if row is None:
            return None
        annual = row[f"band_{letter.lower()}"]
        if annual is None:
            return None
        return round(annual / 12)
    finally:
        conn.close()
