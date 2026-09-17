import pytest

from app.field_colors import store
from app.field_colors.broadband import parse_broadband_mbps
from app.field_colors.evaluate import color_for, colors_for_listing
from app.listings import store as listings_store


# --- store: CRUD -------------------------------------------------------

def test_upsert_and_list_numeric_threshold():
    rule = store.upsert_threshold("floor_area_sqft", "700", "500", True)
    assert rule["field"] == "floor_area_sqft"
    assert rule["green_cutoff"] == "700"
    assert rule["red_cutoff"] == "500"
    assert rule["higher_is_better"] == 1
    assert store.list_thresholds() == [rule]


def test_upsert_replaces_existing_row_for_same_field():
    store.upsert_threshold("floor_area_sqft", "700", "500", True)
    updated = store.upsert_threshold("floor_area_sqft", "800", "600", True)
    assert updated["green_cutoff"] == "800"
    assert len(store.list_thresholds()) == 1


def test_upsert_rejects_unknown_field():
    with pytest.raises(ValueError, match="unknown field-color field"):
        store.upsert_threshold("not_a_field", "1", "2", True)


def test_upsert_numeric_requires_direction():
    with pytest.raises(ValueError, match="higher_is_better is required"):
        store.upsert_threshold("floor_area_sqft", "700", "500", None)


def test_upsert_numeric_rejects_non_numeric_cutoff():
    with pytest.raises(ValueError, match="not numeric"):
        store.upsert_threshold("floor_area_sqft", "not-a-number", None, True)


def test_upsert_epc_band_normalizes_case():
    rule = store.upsert_threshold("epc_current", "c", "e", None)
    assert rule["green_cutoff"] == "C"
    assert rule["red_cutoff"] == "E"
    assert rule["higher_is_better"] is None


def test_upsert_epc_band_rejects_invalid_band():
    with pytest.raises(ValueError, match="not an EPC band"):
        store.upsert_threshold("epc_current", "Z", None, None)


def test_upsert_epc_band_rejects_direction():
    with pytest.raises(ValueError, match="fixed band order"):
        store.upsert_threshold("epc_current", "C", "E", True)


def test_upsert_allows_one_sided_cutoff():
    rule = store.upsert_threshold("price_gbp", None, "700000", False)
    assert rule["green_cutoff"] is None
    assert rule["red_cutoff"] == "700000"


def test_delete_threshold():
    store.upsert_threshold("floor_area_sqft", "700", "500", True)
    store.delete_threshold("floor_area_sqft")
    assert store.list_thresholds() == []


def test_delete_threshold_unknown_field_is_a_no_op():
    # No row to delete either way -- DELETE on a field outside the registry
    # (or just one with no stored row) silently succeeds rather than 404ing,
    # same idempotent-delete precedent as standards_rules.delete_rule.
    store.delete_threshold("not_a_field")
    assert store.list_thresholds() == []


@pytest.mark.parametrize("bad_value", ["nan", "inf", "-inf", "Infinity"])
def test_upsert_numeric_rejects_non_finite_cutoff(bad_value):
    with pytest.raises(ValueError, match="not a finite number"):
        store.upsert_threshold("floor_area_sqft", bad_value, None, True)


# --- evaluate: numeric ---------------------------------------------------

def test_color_for_numeric_lower_is_better_green():
    rule = {"green_cutoff": "600000", "red_cutoff": "700000", "higher_is_better": 0}
    assert color_for("price_gbp", 600000, rule) == "green"  # inclusive
    assert color_for("price_gbp", 500000, rule) == "green"


def test_color_for_numeric_lower_is_better_red():
    rule = {"green_cutoff": "600000", "red_cutoff": "700000", "higher_is_better": 0}
    assert color_for("price_gbp", 700000, rule) == "red"  # inclusive
    assert color_for("price_gbp", 800000, rule) == "red"


def test_color_for_numeric_lower_is_better_amber():
    rule = {"green_cutoff": "600000", "red_cutoff": "700000", "higher_is_better": 0}
    assert color_for("price_gbp", 650000, rule) == "amber"


def test_color_for_numeric_higher_is_better():
    rule = {"green_cutoff": "950", "red_cutoff": "750", "higher_is_better": 1}
    assert color_for("floor_area_sqft", 1000, rule) == "green"
    assert color_for("floor_area_sqft", 950, rule) == "green"
    assert color_for("floor_area_sqft", 700, rule) == "red"
    assert color_for("floor_area_sqft", 750, rule) == "red"
    assert color_for("floor_area_sqft", 850, rule) == "amber"


def test_color_for_numeric_missing_value_is_none():
    rule = {"green_cutoff": "950", "red_cutoff": "750", "higher_is_better": 1}
    assert color_for("floor_area_sqft", None, rule) is None


def test_color_for_no_rule_is_none():
    assert color_for("floor_area_sqft", 1000, None) is None


def test_color_for_one_sided_cutoff_only_evaluates_that_side():
    rule = {"green_cutoff": None, "red_cutoff": "700000", "higher_is_better": 0}
    assert color_for("price_gbp", 800000, rule) == "red"
    assert color_for("price_gbp", 100, rule) == "amber"  # no green rule -> never green


# --- evaluate: epc_band ---------------------------------------------------

def test_color_for_epc_band_green():
    rule = {"green_cutoff": "C", "red_cutoff": "E", "higher_is_better": None}
    assert color_for("epc_current", "A (90)", rule) == "green"
    assert color_for("epc_current", "C (70)", rule) == "green"


def test_color_for_epc_band_red():
    rule = {"green_cutoff": "C", "red_cutoff": "E", "higher_is_better": None}
    assert color_for("epc_current", "E (40)", rule) == "red"
    assert color_for("epc_current", "G (10)", rule) == "red"


def test_color_for_epc_band_amber():
    rule = {"green_cutoff": "C", "red_cutoff": "E", "higher_is_better": None}
    assert color_for("epc_current", "D (58)", rule) == "amber"


def test_color_for_epc_band_one_sided_cutoff_only_evaluates_that_side():
    rule = {"green_cutoff": None, "red_cutoff": "E", "higher_is_better": None}
    assert color_for("epc_current", "G (10)", rule) == "red"
    assert color_for("epc_current", "A (95)", rule) == "amber"  # no green rule -> never green


def test_color_for_numeric_both_cutoffs_none_is_always_amber():
    # Reachable via a raw PUT with both cutoffs omitted (the admin panel
    # avoids this shape by DELETEing instead) -- every value for that field
    # is stuck on "amber" forever, never green or red.
    rule = {"green_cutoff": None, "red_cutoff": None, "higher_is_better": True}
    assert color_for("floor_area_sqft", 1, rule) == "amber"
    assert color_for("floor_area_sqft", 1_000_000, rule) == "amber"


# --- evaluate: colors_for_listing -----------------------------------------

def test_colors_for_listing_mirrors_service_charge_pm_from_pa():
    listing = {"service_charge_pa": 4000, "service_charge_pm": 333}
    rules = [{"field": "service_charge_pa", "green_cutoff": "2500", "red_cutoff": "4000", "higher_is_better": 0}]
    colors = colors_for_listing(listing, rules)
    assert colors["service_charge_pa"] == "red"
    assert colors["service_charge_pm"] == "red"


def test_colors_for_listing_omits_fields_with_no_colour():
    listing = {"floor_area_sqft": None, "price_gbp": 500000}
    rules = [
        {"field": "floor_area_sqft", "green_cutoff": "950", "red_cutoff": "750", "higher_is_better": 1},
        {"field": "price_gbp", "green_cutoff": "600000", "red_cutoff": "700000", "higher_is_better": 0},
    ]
    colors = colors_for_listing(listing, rules)
    assert "floor_area_sqft" not in colors
    assert colors["price_gbp"] == "green"


# --- broadband parsing -----------------------------------------------------

@pytest.mark.parametrize(
    "raw,expected",
    [
        ("900Mb", 900),
        ("900 Mb", 900),
        ("900Mbps", 900),
        ("63.5Mb", 64),
        (None, None),
        ("", None),
        ("no unit here", None),
    ],
)
def test_parse_broadband_mbps(raw, expected):
    assert parse_broadband_mbps(raw) == expected


# --- routes: /api/admin/field-color-thresholds ------------------------------

def test_upsert_threshold_route(client):
    resp = client.put(
        "/api/admin/field-color-thresholds/floor_area_sqft",
        json={"green_cutoff": "950", "red_cutoff": "750", "higher_is_better": True},
    )
    assert resp.status_code == 200
    assert resp.json()["field"] == "floor_area_sqft"


def test_upsert_threshold_route_invalid_returns_422(client):
    resp = client.put(
        "/api/admin/field-color-thresholds/not_a_field",
        json={"green_cutoff": "1", "red_cutoff": "2", "higher_is_better": True},
    )
    assert resp.status_code == 422


def test_list_thresholds_route(client):
    client.put(
        "/api/admin/field-color-thresholds/floor_area_sqft",
        json={"green_cutoff": "950", "red_cutoff": "750", "higher_is_better": True},
    )
    resp = client.get("/api/admin/field-color-thresholds")
    assert resp.status_code == 200
    assert len(resp.json()) == 1


def test_delete_threshold_route(client):
    client.put(
        "/api/admin/field-color-thresholds/floor_area_sqft",
        json={"green_cutoff": "950", "red_cutoff": "750", "higher_is_better": True},
    )
    resp = client.delete("/api/admin/field-color-thresholds/floor_area_sqft")
    assert resp.status_code == 204
    assert client.get("/api/admin/field-color-thresholds").json() == []


# --- listing detail integration --------------------------------------------

def test_get_listing_includes_field_colors(client):
    listings_store.create_stub_listing(1, "https://www.rightmove.co.uk/properties/1")
    listings_store.apply_extracted_fields(1, {"floor_area_sqft": 1000})
    client.put(
        "/api/admin/field-color-thresholds/floor_area_sqft",
        json={"green_cutoff": "950", "red_cutoff": "750", "higher_is_better": True},
    )

    resp = client.get("/api/listings/1")
    assert resp.status_code == 200
    assert resp.json()["field_colors"]["floor_area_sqft"] == "green"


def test_get_listing_no_field_colors_when_no_rules(client):
    listings_store.create_stub_listing(1, "https://www.rightmove.co.uk/properties/1")
    listings_store.apply_extracted_fields(1, {"floor_area_sqft": 1000})

    resp = client.get("/api/listings/1")
    assert resp.json()["field_colors"] == {}


def test_get_listing_mirrors_service_charge_pm_color_from_pa(client):
    listings_store.create_stub_listing(1, "https://www.rightmove.co.uk/properties/1")
    listings_store.apply_extracted_fields(1, {"service_charge_pa": 4000, "service_charge_pm": 333})
    client.put(
        "/api/admin/field-color-thresholds/service_charge_pa",
        json={"green_cutoff": "2500", "red_cutoff": "4000", "higher_is_better": False},
    )

    resp = client.get("/api/listings/1")
    colors = resp.json()["field_colors"]
    assert colors["service_charge_pa"] == "red"
    assert colors["service_charge_pm"] == "red"
