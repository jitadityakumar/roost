"""listings.epc_certificate_url / epc_certificate_data persistence (issue #115).

The certificate's ratings are written onto epc_current/epc_potential and
deliberately bypass manual-edit stickiness (the user decided a certificate
outranks both LLM and hand-entered values). listings.epc_source has a CHECK
limited to ('rightmove', 'llm') and widening it would mean rebuilding the
whole listings table, so it is left untouched here: the API reports
epc_source='certificate' at serialization time instead (listings/serialize.py)
and clear() NULLs the stored one. While
a certificate URL is set, scrapes and the epc_vision job are blocked from
overwriting them (listings.store.apply_extracted_fields) and PATCH refuses
manual edits of them (routes/listings.py).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from app.db.connection import get_connection

JOB_TYPE = "epc_certificate_fetch"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def set_url(listing_id: int, url: str) -> None:
    """Attach (or replace) the certificate URL, discarding any previously
    parsed data -- it belonged to a different certificate. If that data had
    supplied the ratings, their stored source label (serialize reports
    'certificate' only while data is present) is NULLed so it can't fall back
    to a stale llm/rightmove claim, including via a later clear()."""
    conn = get_connection()
    try:
        conn.execute(
            """
            UPDATE listings
            SET epc_source = CASE WHEN epc_certificate_data IS NOT NULL THEN NULL ELSE epc_source END,
                epc_certificate_url = ?, epc_certificate_data = NULL, updated_at = ?
            WHERE id = ?
            """,
            (url, _now_iso(), listing_id),
        )
        conn.commit()
    finally:
        conn.close()


def clear(listing_id: int) -> None:
    """Detach the certificate. The ratings it wrote stay in place (and become
    editable again); only the URL, parsed data and its fetch-job history go,
    so a stale failed job can't keep the pipeline badge red."""
    conn = get_connection()
    try:
        # If a certificate had supplied the ratings, their old llm/rightmove
        # source label no longer describes them -- NULL it (CHECK allows it).
        conn.execute(
            """
            UPDATE listings
            SET epc_source = CASE WHEN epc_certificate_data IS NOT NULL THEN NULL ELSE epc_source END,
                epc_certificate_url = NULL, epc_certificate_data = NULL, updated_at = ?
            WHERE id = ?
            """,
            (_now_iso(), listing_id),
        )
        conn.execute("DELETE FROM jobs WHERE listing_id = ? AND job_type = ?", (listing_id, JOB_TYPE))
        conn.commit()
    finally:
        conn.close()


def save_parsed(listing_id: int, url: str, data: dict) -> bool:
    """Store the parsed certificate and apply its ratings, only if the
    listing's URL is still `url` (the user may have replaced or removed it
    while the fetch was in flight). Returns whether anything was written."""
    now = _now_iso()
    payload = dict(data, fetched_at=now)
    conn = get_connection()
    try:
        cur = conn.execute(
            """
            UPDATE listings
            SET epc_certificate_data = ?, epc_current = ?, epc_potential = ?, updated_at = ?
            WHERE id = ? AND epc_certificate_url = ?
            """,
            (
                json.dumps(payload),
                f"{data['current_rating']} ({data['current_score']})",
                f"{data['potential_rating']} ({data['potential_score']})"
                if data.get("potential_rating") and data.get("potential_score") is not None
                else None,
                now,
                listing_id,
                url,
            ),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()
