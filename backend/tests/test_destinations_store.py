import pytest

from app.destinations import store


def test_create_and_list_destination():
    d = store.create_destination("Office", "pad", "Paddington", 0, "08:30")
    assert d["name"] == "Office"
    assert d["crs"] == "PAD"
    assert d["station_name"] == "Paddington"
    assert d["day_of_week"] == 0
    assert d["time"] == "08:30"
    assert d["enabled"] == 1
    assert store.list_destinations() == [d]


def test_create_destination_rejects_blank_name():
    with pytest.raises(ValueError, match="name is required"):
        store.create_destination("  ", "PAD", "Paddington", 0, "08:30")


def test_create_destination_rejects_invalid_day_of_week():
    with pytest.raises(ValueError, match="day_of_week"):
        store.create_destination("Office", "PAD", "Paddington", 7, "08:30")


def test_create_destination_rejects_invalid_time():
    with pytest.raises(ValueError, match="not a valid 24h HH:MM time"):
        store.create_destination("Office", "PAD", "Paddington", 0, "8:30")
    with pytest.raises(ValueError, match="not a valid 24h HH:MM time"):
        store.create_destination("Office", "PAD", "Paddington", 0, "25:00")


def test_update_destination_toggle_enabled():
    d = store.create_destination("Office", "PAD", "Paddington", 0, "08:30")
    disabled = store.update_destination(d["id"], enabled=False)
    assert disabled["enabled"] == 0


def test_update_destination_validates_merged_row():
    d = store.create_destination("Office", "PAD", "Paddington", 0, "08:30")
    with pytest.raises(ValueError, match="not a valid 24h HH:MM time"):
        store.update_destination(d["id"], time="nope")


def test_update_unknown_destination_returns_none():
    assert store.update_destination(999, enabled=False) is None


def test_delete_destination():
    d = store.create_destination("Office", "PAD", "Paddington", 0, "08:30")
    store.delete_destination(d["id"])
    assert store.list_destinations() == []
