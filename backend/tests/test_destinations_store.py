import pytest

from app import config
from app.destinations import journey_store, store


def test_create_and_list_station_destination():
    d = store.create_destination("Office", "station", "910GPADTON", "Paddington", 0, "08:30")
    assert d["name"] == "Office"
    assert d["destination_type"] == "station"
    assert d["tfl_identifier"] == "910GPADTON"
    assert d["station_name"] == "Paddington"
    assert d["day_of_week"] == 0
    assert d["time"] == "08:30"
    assert d["enabled"] == 1
    assert store.list_destinations() == [d]


def test_create_and_list_postcode_destination():
    d = store.create_destination("Zappi", "postcode", "NW1 7JN", "NW1 7JN", 1, "18:00")
    assert d["destination_type"] == "postcode"
    assert d["tfl_identifier"] == "NW1 7JN"
    assert d["station_name"] == "NW1 7JN"


def test_create_destination_rejects_blank_name():
    with pytest.raises(ValueError, match="name is required"):
        store.create_destination("  ", "station", "910GPADTON", "Paddington", 0, "08:30")


def test_create_destination_rejects_invalid_destination_type():
    with pytest.raises(ValueError, match="destination_type"):
        store.create_destination("Office", "bogus", "910GPADTON", "Paddington", 0, "08:30")


def test_create_destination_rejects_invalid_day_of_week():
    with pytest.raises(ValueError, match="day_of_week"):
        store.create_destination("Office", "station", "910GPADTON", "Paddington", 7, "08:30")


def test_create_destination_rejects_invalid_time():
    with pytest.raises(ValueError, match="not a valid 24h HH:MM time"):
        store.create_destination("Office", "station", "910GPADTON", "Paddington", 0, "8:30")
    with pytest.raises(ValueError, match="not a valid 24h HH:MM time"):
        store.create_destination("Office", "station", "910GPADTON", "Paddington", 0, "25:00")


def test_update_destination_toggle_enabled():
    d = store.create_destination("Office", "station", "910GPADTON", "Paddington", 0, "08:30")
    disabled = store.update_destination(d["id"], enabled=False)
    assert disabled["enabled"] == 0


def test_update_destination_validates_merged_row():
    d = store.create_destination("Office", "station", "910GPADTON", "Paddington", 0, "08:30")
    with pytest.raises(ValueError, match="not a valid 24h HH:MM time"):
        store.update_destination(d["id"], time="nope")


def test_update_destination_rejects_invalid_destination_type():
    d = store.create_destination("Office", "station", "910GPADTON", "Paddington", 0, "08:30")
    with pytest.raises(ValueError, match="destination_type"):
        store.update_destination(d["id"], destination_type="bogus")


def test_update_unknown_destination_returns_none():
    assert store.update_destination(999, enabled=False) is None


def test_update_destination_normalizes_name_tfl_identifier_station_name():
    d = store.create_destination("Office", "station", "910GPADTON", "Paddington", 0, "08:30")
    updated = store.update_destination(
        d["id"], tfl_identifier=" 910GPADTON ", name="  Work  ", station_name="  Paddington  "
    )
    assert updated["tfl_identifier"] == "910GPADTON"
    assert updated["name"] == "Work"
    assert updated["station_name"] == "Paddington"


def test_delete_destination():
    d = store.create_destination("Office", "station", "910GPADTON", "Paddington", 0, "08:30")
    store.delete_destination(d["id"])
    assert store.list_destinations() == []


def test_delete_destination_clears_home_journey(monkeypatch):
    # get_home_journeys() short-circuits to {} without touching the DB when
    # home isn't configured (journey_store.py) -- home must be configured
    # here or this assertion would pass vacuously regardless of whether the
    # delete actually cascaded.
    monkeypatch.setattr(config, "HOME_LAT", 51.465)
    monkeypatch.setattr(config, "HOME_LON", -0.2407)
    d = store.create_destination("Office", "station", "910GPADTON", "Paddington", 0, "08:30")
    journey_store.set_home_journey(d["id"], {"duration_minutes": 42, "kind": "direct", "num_changes": 0})
    assert journey_store.get_home_journeys() != {}

    store.delete_destination(d["id"])

    assert journey_store.get_home_journeys() == {}
