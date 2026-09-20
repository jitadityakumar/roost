"""Local-politics reference data (issue #61): council_composition and
constituency_mp, both keyed by GSS code. See migration 0036."""
from __future__ import annotations

import csv
import io
import json
from datetime import datetime, timezone

from app.db.connection import get_connection

# CSV column -> display name. Order is only a tiebreak; the table sorts by seats.
PARTIES = {
    "con": "Conservative",
    "lab": "Labour",
    "ld": "Liberal Democrats",
    "green": "Green",
    "ref": "Reform UK",
    "snp": "SNP",
    "pc": "Plaid Cymru",
    "ukip": "UKIP",
    "other": "Other",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _to_int(value: str) -> int:
    value = (value or "").strip()
    return int(value) if value else 0


def _seats(row: dict) -> dict:
    return {key: _to_int(row.get(key)) for key in PARTIES}


def import_council_csv(text: str) -> int:
    """Imports the Open Council Data UK history CSV once (never re-downloaded
    by the app). One row per council per year; only the latest year's rows
    carry a GSS code (last column), so that year is the import target and the
    year before it, linked via the CSV's stable `council id` column (not the
    name), becomes the "previous" comparison. A council with no GSS on its
    latest row is skipped (empty state in the UI, no name-matching fallback).
    Returns the number of councils imported."""
    rows = list(csv.DictReader(io.StringIO(text)))
    # The header has a trailing unnamed column holding the GSS code.
    gss_key = next(k for k in rows[0] if not (k or "").strip()) if rows else None
    if gss_key is None:
        return 0
    with_gss = [r for r in rows if (r.get(gss_key) or "").strip()]
    if not with_gss:
        return 0
    latest_year = max(int(r["year"]) for r in with_gss)
    by_council_year = {(r["council id"], int(r["year"])): r for r in rows}

    conn = get_connection()
    try:
        count = 0
        for row in with_gss:
            if int(row["year"]) != latest_year:
                continue
            prev = by_council_year.get((row["council id"], latest_year - 1))
            previous_json = (
                json.dumps({"year": latest_year - 1, "total": _to_int(prev["total"]), "parties": _seats(prev)})
                if prev
                else None
            )
            seats = _seats(row)
            conn.execute(
                f"""
                INSERT INTO council_composition
                    (gss_code, council_id, authority, year, total, {", ".join(PARTIES)}, previous_json)
                VALUES (?, ?, ?, ?, ?, {", ".join("?" for _ in PARTIES)}, ?)
                ON CONFLICT(gss_code) DO UPDATE SET
                    council_id = excluded.council_id, authority = excluded.authority,
                    year = excluded.year, total = excluded.total,
                    {", ".join(f"{k} = excluded.{k}" for k in PARTIES)},
                    previous_json = excluded.previous_json
                """,
                (
                    row[gss_key].strip(),
                    int(row["council id"]),
                    row["authority"],
                    latest_year,
                    _to_int(row["total"]),
                    *seats.values(),
                    previous_json,
                ),
            )
            count += 1
        conn.commit()
        return count
    finally:
        conn.close()


def get_composition(gss_code: str | None) -> dict | None:
    if not gss_code:
        return None
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM council_composition WHERE gss_code = ?", (gss_code,)).fetchone()
        if row is None:
            return None
        return {
            "authority": row["authority"],
            "year": row["year"],
            "total": row["total"],
            "parties": {key: row[key] for key in PARTIES},
            "previous": json.loads(row["previous_json"]) if row["previous_json"] else None,
        }
    finally:
        conn.close()


def has_mp(constituency_gss: str) -> bool:
    conn = get_connection()
    try:
        return (
            conn.execute(
                "SELECT 1 FROM constituency_mp WHERE constituency_gss = ?", (constituency_gss,)
            ).fetchone()
            is not None
        )
    finally:
        conn.close()


def upsert_mp(constituency_gss: str, constituency_name: str, mp: dict) -> None:
    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO constituency_mp
                (constituency_gss, constituency_name, members_api_id, member_id, member_name,
                 party_name, party_abbreviation, party_colour, result, majority, turnout,
                 electorate, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(constituency_gss) DO UPDATE SET
                constituency_name = excluded.constituency_name,
                members_api_id = excluded.members_api_id, member_id = excluded.member_id,
                member_name = excluded.member_name, party_name = excluded.party_name,
                party_abbreviation = excluded.party_abbreviation,
                party_colour = excluded.party_colour, result = excluded.result,
                majority = excluded.majority, turnout = excluded.turnout,
                electorate = excluded.electorate, updated_at = excluded.updated_at
            """,
            (
                constituency_gss,
                constituency_name,
                mp["members_api_id"],
                mp["member_id"],
                mp["member_name"],
                mp["party_name"],
                mp["party_abbreviation"],
                mp["party_colour"],
                mp["result"],
                mp["majority"],
                mp["turnout"],
                mp["electorate"],
                _now_iso(),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def get_mp(constituency_gss: str | None) -> dict | None:
    if not constituency_gss:
        return None
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM constituency_mp WHERE constituency_gss = ?", (constituency_gss,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()
