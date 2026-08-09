import pytest

from app.crime import store


def test_create_and_list_baseline():
    baseline = store.create_baseline("Home", "ZZ1 1AA")
    assert baseline["label"] == "Home"
    assert baseline["postcode"] == "ZZ1 1AA"
    assert store.list_baselines() == [baseline]


def test_create_baseline_rejects_a_fourth():
    store.create_baseline("A", "ZZ1 1AA")
    store.create_baseline("B", "ZZ3 3CC")
    store.create_baseline("C", "ZZ4 4DD")
    with pytest.raises(ValueError, match="only 3 baselines"):
        store.create_baseline("D", "ZZ2 2BB")


def test_delete_baseline():
    baseline = store.create_baseline("Home", "ZZ1 1AA")
    store.delete_baseline(baseline["id"])
    assert store.list_baselines() == []


def test_get_cached_stats_returns_none_when_absent():
    assert store.get_cached_stats("ZZ1 1AA") is None


def test_save_and_get_cached_stats():
    saved = store.save_stats("ZZ1 1AA", 51.4, -0.2, {"burglary": 3})
    fetched = store.get_cached_stats("ZZ1 1AA")
    assert fetched["category_counts"] == {"burglary": 3}
    assert fetched["lat"] == 51.4
    assert fetched["fetched_at"] == saved["fetched_at"]


def test_cache_lookup_normalizes_postcode_spacing_and_case():
    store.save_stats("ZZ1 1AA", 51.4, -0.2, {"burglary": 3})
    assert store.get_cached_stats("zz11aa") is not None
    assert store.get_cached_stats("  zz1   1aa  ") is not None


def test_save_stats_overwrites_existing_row_for_same_postcode():
    store.save_stats("ZZ1 1AA", 51.4, -0.2, {"burglary": 3})
    store.save_stats("zz1 1aa", 51.5, -0.3, {"burglary": 9})
    fetched = store.get_cached_stats("ZZ1 1AA")
    assert fetched["category_counts"] == {"burglary": 9}
    assert fetched["lat"] == 51.5
