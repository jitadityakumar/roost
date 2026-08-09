"""Single entry point for getting crime stats for a postcode -- reads the
cache, re-fetching from the live APIs only if there's no cached row or it's
stale. Used by both baseline creation (so a bad postcode / API failure
surfaces immediately in the admin UI) and the per-listing crime route."""
from datetime import datetime, timedelta, timezone

from app.crime import client, store

CACHE_MAX_AGE_DAYS = 30


def _is_stale(fetched_at: str) -> bool:
    fetched = datetime.fromisoformat(fetched_at)
    return datetime.now(timezone.utc) - fetched > timedelta(days=CACHE_MAX_AGE_DAYS)


def get_or_refresh_stats(postcode: str) -> dict:
    cached = store.get_cached_stats(postcode)
    if cached is not None and not _is_stale(cached["fetched_at"]):
        return cached

    lat, lng = client.geocode_postcode(postcode)
    category_counts = client.fetch_category_counts(lat, lng)
    return store.save_stats(postcode, lat, lng, category_counts)
