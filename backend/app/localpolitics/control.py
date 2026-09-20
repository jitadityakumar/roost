"""Council control computed from seat counts (issue #61) -- deliberately not
the CSV's own control label, which encodes mayors/coalitions we can't show."""
from __future__ import annotations

from app.localpolitics.store import PARTIES


def majority_threshold(total: int) -> int:
    return total // 2 + 1


def headline(total: int, parties: dict) -> dict:
    """{"status": "majority"|"no_overall_majority", "party": name|None,
    "seats": int|None, "total": int}. For a majority, `party` holds it; for
    no overall majority, `party` is the largest party, or None on an exact
    tie for most seats."""
    ranked = sorted(parties.items(), key=lambda kv: kv[1], reverse=True)
    top_key, top_seats = ranked[0]
    if top_seats >= majority_threshold(total):
        return {"status": "majority", "party": PARTIES[top_key], "seats": top_seats, "total": total}
    tied = len(ranked) > 1 and ranked[1][1] == top_seats
    return {
        "status": "no_overall_majority",
        "party": None if tied else PARTIES[top_key],
        "seats": None if tied else top_seats,
        "total": total,
    }


def party_rows(total: int, parties: dict, previous: dict | None) -> list[dict]:
    """One row per party with seats now or in the previous year, biggest
    first. `change` is None when there's no previous-year row at all."""
    prev_parties = previous["parties"] if previous else None
    rows = []
    for key, name in PARTIES.items():
        seats = parties[key]
        prev_seats = prev_parties[key] if prev_parties else None
        if seats == 0 and not prev_seats:
            continue
        rows.append(
            {
                "key": key,
                "name": name,
                "seats": seats,
                "share": round(seats / total * 100) if total else 0,
                "previous_seats": prev_seats,
                "change": seats - prev_seats if prev_seats is not None else None,
            }
        )
    rows.sort(key=lambda r: r["seats"], reverse=True)
    return rows
