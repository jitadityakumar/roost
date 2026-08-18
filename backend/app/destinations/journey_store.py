"""Plain CRUD for destination_journeys (migration 0014) and journey_scan_pools
(migration 0021, issue #59). A listing's rows are deleted and reinserted
wholesale on each recompute, not upserted individually -- same precedent as
app/commute/walk_store.py."""
from __future__ import annotations

import json
from datetime import datetime, timezone

from app import config
from app.db.connection import get_connection


def replace_journeys(listing_id: int, entries: list[tuple[dict, dict | None]]) -> None:
    """entries: [(row_dict, pool_dict_or_None), ...] -- row_dict is
    {"destination_id", "duration_minutes", "kind", "num_changes", "operator",
    "origin_crs", "origin_name", "arrival_name", "interchange_crs",
    "departure_time", "arrival_time"}; pool_dict is
    {"query_params", "candidate_pool"} or None. Replaces destination_journeys
    AND journey_scan_pools wholesale for this listing -- clearing every
    existing pool row first, even for a destination not present in `entries`
    at all (e.g. no lat/lon, disabled), is what makes stale-pool clearing
    correct across every compute.py path without having to enumerate them
    here."""
    now = datetime.now(timezone.utc).isoformat()
    conn = get_connection()
    try:
        conn.execute("DELETE FROM destination_journeys WHERE listing_id = ?", (listing_id,))
        conn.execute("DELETE FROM journey_scan_pools WHERE listing_id = ?", (listing_id,))
        conn.executemany(
            "INSERT INTO destination_journeys "
            "(listing_id, destination_id, duration_minutes, kind, num_changes, operator, "
            "origin_crs, origin_name, arrival_name, interchange_crs, departure_time, arrival_time, computed_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    listing_id,
                    row["destination_id"],
                    row["duration_minutes"],
                    row["kind"],
                    row["num_changes"],
                    row["operator"],
                    row["origin_crs"],
                    row["origin_name"],
                    row.get("arrival_name"),
                    row.get("interchange_crs"),
                    row["departure_time"],
                    row["arrival_time"],
                    now,
                )
                for row, _pool in entries
            ],
        )
        pool_rows = [
            (
                listing_id,
                row["destination_id"],
                now,
                json.dumps(pool["query_params"]),
                json.dumps(pool["candidate_pool"]),
            )
            for row, pool in entries
            if pool is not None
        ]
        if pool_rows:
            conn.executemany(
                "INSERT INTO journey_scan_pools "
                "(listing_id, destination_id, scanned_at, query_params, candidate_pool) "
                "VALUES (?, ?, ?, ?, ?)",
                pool_rows,
            )
        conn.commit()
    finally:
        conn.close()


def get_journeys(listing_id: int) -> dict[int, dict]:
    """Returns {destination_id: row_dict}."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM destination_journeys WHERE listing_id = ?", (listing_id,)
        ).fetchall()
        return {r["destination_id"]: dict(r) for r in rows}
    finally:
        conn.close()


def replace_single(listing_id: int, destination_id: int, row: dict | None, pool: dict | None = None) -> None:
    """Delete-then-reinsert for exactly one (listing_id, destination_id)
    pair, leaving every other destination's stored row for this listing
    untouched -- used by compute_for_destination's per-destination backfill,
    where replace_journeys' whole-listing wipe would be wrong (it would
    discard every other destination's already-computed result). `row` is
    the same shape as replace_journeys' row dicts, minus "destination_id"
    (redundant with the argument); None just clears the row. `pool` is
    {"query_params", "candidate_pool"} or None -- also cleared and
    reinserted alongside `row`, so a destination that goes from resolved to
    unresolved (or vice versa) never leaves a stale journey_scan_pools row
    behind."""
    now = datetime.now(timezone.utc).isoformat()
    conn = get_connection()
    try:
        conn.execute(
            "DELETE FROM destination_journeys WHERE listing_id = ? AND destination_id = ?",
            (listing_id, destination_id),
        )
        conn.execute(
            "DELETE FROM journey_scan_pools WHERE listing_id = ? AND destination_id = ?",
            (listing_id, destination_id),
        )
        if row is not None:
            conn.execute(
                "INSERT INTO destination_journeys "
                "(listing_id, destination_id, duration_minutes, kind, num_changes, operator, "
                "origin_crs, origin_name, arrival_name, interchange_crs, departure_time, arrival_time, computed_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    listing_id,
                    destination_id,
                    row["duration_minutes"],
                    row["kind"],
                    row["num_changes"],
                    row["operator"],
                    row["origin_crs"],
                    row["origin_name"],
                    row.get("arrival_name"),
                    row.get("interchange_crs"),
                    row["departure_time"],
                    row["arrival_time"],
                    now,
                ),
            )
        if row is not None and pool is not None:
            conn.execute(
                "INSERT INTO journey_scan_pools "
                "(listing_id, destination_id, scanned_at, query_params, candidate_pool) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    listing_id,
                    destination_id,
                    now,
                    json.dumps(pool["query_params"]),
                    json.dumps(pool["candidate_pool"]),
                ),
            )
        conn.commit()
    finally:
        conn.close()


def delete_for_destination(listing_id: int, destination_id: int) -> None:
    replace_single(listing_id, destination_id, None)


def get_scan_pool_ids(listing_id: int) -> dict[int, int]:
    """{destination_id: journey_scan_pools.id} for one listing -- mirrors
    get_journeys' shape, used by routes/destination_journeys.py to expose
    which destinations have a details link."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT destination_id, id FROM journey_scan_pools WHERE listing_id = ?", (listing_id,)
        ).fetchall()
        return {r["destination_id"]: r["id"] for r in rows}
    finally:
        conn.close()


def get_scan_pool(pool_id: int) -> dict | None:
    """One full pool row by id, JSON columns parsed, or None if missing."""
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM journey_scan_pools WHERE id = ?", (pool_id,)).fetchone()
        if row is None:
            return None
        d = dict(row)
        d["query_params"] = json.loads(d["query_params"])
        d["candidate_pool"] = json.loads(d["candidate_pool"])
        return d
    finally:
        conn.close()


def set_home_journey(destination_id: int, journey: dict | None) -> None:
    """journey: {"duration_minutes", "kind", "num_changes"} (extra keys, e.g.
    from a full _journey_row dict, are ignored) -- or None to clear. Same
    delete-then-reinsert precedent as replace_single, just keyed by
    destination_id alone since home has one row per destination, not per
    listing."""
    now = datetime.now(timezone.utc).isoformat()
    conn = get_connection()
    try:
        conn.execute("DELETE FROM home_journeys WHERE destination_id = ?", (destination_id,))
        if journey is not None:
            conn.execute(
                "INSERT INTO home_journeys (destination_id, duration_minutes, kind, num_changes, computed_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (destination_id, journey["duration_minutes"], journey["kind"], journey["num_changes"], now),
            )
        conn.commit()
    finally:
        conn.close()


def get_home_journeys() -> dict[int, dict]:
    """Returns {destination_id: row_dict} for every destination with a
    stored home journey. Short-circuits without touching the DB if home
    isn't configured at all (config.HOME_LAT/LON unset) -- the expected
    state on most deployments, see config.py -- since the table is
    necessarily empty then anyway (compute_home_journey clears/never writes
    a row in that case)."""
    if config.HOME_LAT is None or config.HOME_LON is None:
        return {}
    conn = get_connection()
    try:
        rows = conn.execute("SELECT * FROM home_journeys").fetchall()
        return {r["destination_id"]: dict(r) for r in rows}
    finally:
        conn.close()


def delete_home_journey(destination_id: int) -> None:
    set_home_journey(destination_id, None)
