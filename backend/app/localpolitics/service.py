"""Resolve + read local politics for a listing (issue #61). Everything the
detail page shows comes from the DB; the only network calls here are the
postcodes.io / Members API resolve steps used at scrape time, on postcode
edit, and by the manual Refresh button."""
from __future__ import annotations

import logging

from app.listings import store as listings_store
from app.localpolitics import control, members_client, store

logger = logging.getLogger(__name__)

COLUMNS = ("admin_ward", "admin_ward_gss", "parish", "admin_county", "constituency", "constituency_gss")


def columns_from_resolved(resolved: dict | None) -> dict:
    """The listing columns to write for a lookup_postcode() result (all None
    for an unresolved postcode -- i.e. clearing stale values). Tolerant of
    a result that only carries the council fields."""
    resolved = resolved or {}
    codes = resolved.get("codes") or {}
    return {
        "admin_ward": resolved.get("admin_ward"),
        "admin_ward_gss": codes.get("admin_ward"),
        "parish": resolved.get("parish"),
        "admin_county": resolved.get("admin_county"),
        "constituency": resolved.get("parliamentary_constituency_2024"),
        "constituency_gss": codes.get("parliamentary_constituency_2024"),
    }


def ensure_mp(constituency_gss: str | None, constituency_name: str | None, force: bool = False) -> str:
    """Resolve the constituency's MP row. Never raises -- an outage must not
    fail a scrape. Returns "skipped" (nothing to resolve, or row already
    stored and not forced), "ok", "not_found" (0 or >1 exact matches; any
    existing row is left alone) or "error" (request failed; existing row
    left alone)."""
    if not constituency_gss or not constituency_name:
        return "skipped"
    if not force and store.has_mp(constituency_gss):
        return "skipped"
    try:
        mp = members_client.find_mp(constituency_name)
    except Exception:
        logger.warning("Members API lookup failed for %r", constituency_name, exc_info=True)
        return "error"
    if mp is None:
        return "not_found"
    store.upsert_mp(constituency_gss, constituency_name, mp)
    return "ok"


def section_payload(listing: dict) -> dict:
    """What GET .../local-politics returns, from stored data only."""
    mp = store.get_mp(listing.get("constituency_gss"))
    composition = store.get_composition(listing.get("admin_district_gss"))

    council = None
    if listing.get("admin_district"):
        council = {
            "name": listing["admin_district"],
            "county": listing.get("admin_county"),
            "ward": listing.get("admin_ward"),
            "parish": listing.get("parish"),
        }

    control_payload = None
    if composition:
        total, parties = composition["total"], composition["parties"]
        control_payload = {
            "year": composition["year"],
            "previous_year": composition["previous"]["year"] if composition["previous"] else None,
            "total": total,
            "majority_threshold": control.majority_threshold(total),
            "headline": control.headline(total, parties),
            "parties": control.party_rows(total, parties, composition["previous"]),
        }

    mp_payload = None
    if mp:
        mp_payload = {
            "name": mp["member_name"],
            "member_id": mp["member_id"],
            "constituency": mp["constituency_name"],
            "party_name": mp["party_name"],
            "party_abbreviation": mp["party_abbreviation"],
            "party_colour": mp["party_colour"],
            "result": mp["result"],
            "majority": mp["majority"],
            "turnout": mp["turnout"],
            "electorate": mp["electorate"],
            "turnout_pct": (
                round(mp["turnout"] / mp["electorate"] * 100, 1)
                if mp["turnout"] is not None and mp["electorate"]
                else None
            ),
            "thumbnail_url": f"https://members-api.parliament.uk/api/Members/{mp['member_id']}/Thumbnail",
        }

    return {
        "mp": mp_payload,
        "council": council,
        "control": control_payload,
        "has_data": bool(mp_payload or council or control_payload),
    }
