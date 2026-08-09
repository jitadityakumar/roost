from datetime import datetime, timedelta, timezone

from app.crime import service, store


def test_get_or_refresh_fetches_when_no_cache(monkeypatch):
    calls = []

    def fake_geocode(postcode):
        calls.append(("geocode", postcode))
        return (51.4, -0.2)

    def fake_fetch(lat, lng):
        calls.append(("fetch", lat, lng))
        return {"burglary": 3}

    monkeypatch.setattr(service.client, "geocode_postcode", fake_geocode)
    monkeypatch.setattr(service.client, "fetch_category_counts", fake_fetch)

    result = service.get_or_refresh_stats("ZZ1 1AA")
    assert result["category_counts"] == {"burglary": 3}
    assert calls == [("geocode", "ZZ1 1AA"), ("fetch", 51.4, -0.2)]


def test_get_or_refresh_returns_fresh_cache_without_fetching(monkeypatch):
    store.save_stats("ZZ1 1AA", 51.4, -0.2, {"burglary": 3})

    def fail_if_called(*args, **kwargs):
        raise AssertionError("should not hit the network for a fresh cache")

    monkeypatch.setattr(service.client, "geocode_postcode", fail_if_called)
    monkeypatch.setattr(service.client, "fetch_category_counts", fail_if_called)

    result = service.get_or_refresh_stats("ZZ1 1AA")
    assert result["category_counts"] == {"burglary": 3}


def test_get_or_refresh_refetches_stale_cache(monkeypatch):
    store.save_stats("ZZ1 1AA", 51.4, -0.2, {"burglary": 3})
    stale = (datetime.now(timezone.utc) - timedelta(days=31)).isoformat()
    conn = store.get_connection()
    conn.execute(
        "UPDATE crime_stats_cache SET fetched_at = ? WHERE postcode = ?",
        (stale, store.normalize_postcode("ZZ1 1AA")),
    )
    conn.commit()
    conn.close()

    monkeypatch.setattr(service.client, "geocode_postcode", lambda pc: (51.4, -0.2))
    monkeypatch.setattr(service.client, "fetch_category_counts", lambda lat, lng: {"burglary": 9})

    result = service.get_or_refresh_stats("ZZ1 1AA")
    assert result["category_counts"] == {"burglary": 9}
