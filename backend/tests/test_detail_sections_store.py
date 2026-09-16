from app.detail_sections import store


def test_get_config_seeded_singleton_defaults(isolated_db):
    config = store.get_config()
    assert config["details_expanded"] is True
    assert config["description_features_expanded"] is True
    assert config["nearest_stations_expanded"] is True
    assert config["floorplans_expanded"] is True
    assert config["epc_expanded"] is False
    assert config["room_sizes_expanded"] is False
    assert config["commute_expanded"] is True
    assert config["frequent_destinations_expanded"] is True
    assert config["mortgage_expanded"] is True
    assert config["crime_expanded"] is False
    assert config["jobs_expanded"] is False


def test_put_config_round_trips(isolated_db):
    values = {f"{key}_expanded": False for key in store.SECTION_KEYS}
    values["commute_expanded"] = True
    updated = store.put_config(values)
    assert updated == values

    reread = store.get_config()
    assert reread == values
