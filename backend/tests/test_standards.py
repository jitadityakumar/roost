import pytest

from app.listings import store as listings_store
from app.standards import store
from app.standards.evaluate import evaluate_listing


# --- store: CRUD ---------------------------------------------------------

def test_create_and_list_rule():
    rule = store.create_rule("floor_area_sqft", "lt", "700")
    assert rule["field"] == "floor_area_sqft"
    assert rule["operator"] == "lt"
    assert rule["value"] == "700"
    assert rule["enabled"] == 1
    assert store.list_rules() == [rule]


def test_create_rule_rejects_unknown_field():
    with pytest.raises(ValueError, match="unknown standards field"):
        store.create_rule("not_a_field", "lt", "700")


def test_create_rule_rejects_operator_not_valid_for_field_type():
    with pytest.raises(ValueError, match="not valid for field"):
        store.create_rule("cash_only", "lt", "true")


def test_create_rule_rejects_non_numeric_value_for_numeric_field():
    with pytest.raises(ValueError, match="not numeric"):
        store.create_rule("floor_area_sqft", "lt", "not-a-number")


def test_create_rule_rejects_non_boolean_value_for_boolean_field():
    with pytest.raises(ValueError, match="not a boolean"):
        store.create_rule("cash_only", "eq", "maybe")


def test_create_rule_epc_band_normalizes_case():
    rule = store.create_rule("epc_current", "gt", "c")
    assert rule["value"] == "C"


def test_create_rule_rejects_invalid_epc_band():
    with pytest.raises(ValueError, match="not an EPC band"):
        store.create_rule("epc_current", "gt", "Z")


def test_update_rule_value():
    rule = store.create_rule("floor_area_sqft", "lt", "700")
    updated = store.update_rule(rule["id"], value="800")
    assert updated["value"] == "800"


def test_update_rule_toggle_enabled():
    rule = store.create_rule("cash_only", "eq", "true")
    disabled = store.update_rule(rule["id"], enabled=False)
    assert disabled["enabled"] == 0
    enabled = store.update_rule(rule["id"], enabled=True)
    assert enabled["enabled"] == 1


def test_update_rule_validates_merged_row():
    rule = store.create_rule("floor_area_sqft", "lt", "700")
    with pytest.raises(ValueError, match="not numeric"):
        store.update_rule(rule["id"], value="nope")


def test_update_unknown_rule_returns_none():
    assert store.update_rule(999, value="700") is None


def test_delete_rule():
    rule = store.create_rule("floor_area_sqft", "lt", "700")
    store.delete_rule(rule["id"])
    assert store.list_rules() == []


# --- evaluate --------------------------------------------------------------

def test_evaluate_numeric_lt_matches():
    listing = {"floor_area_sqft": 650}
    rules = [{"id": 1, "field": "floor_area_sqft", "operator": "lt", "value": "700", "enabled": 1}]
    violations = evaluate_listing(listing, rules)
    assert len(violations) == 1
    assert violations[0]["rule_id"] == 1
    assert "700" in violations[0]["message"]


def test_evaluate_numeric_lt_does_not_match():
    listing = {"floor_area_sqft": 750}
    rules = [{"id": 1, "field": "floor_area_sqft", "operator": "lt", "value": "700", "enabled": 1}]
    assert evaluate_listing(listing, rules) == []


def test_evaluate_boolean_eq_true_matches():
    listing = {"cash_only": 1}
    rules = [{"id": 1, "field": "cash_only", "operator": "eq", "value": "true", "enabled": 1}]
    violations = evaluate_listing(listing, rules)
    assert len(violations) == 1


def test_evaluate_boolean_eq_false_does_not_match_when_true():
    listing = {"cash_only": 1}
    rules = [{"id": 1, "field": "cash_only", "operator": "eq", "value": "false", "enabled": 1}]
    assert evaluate_listing(listing, rules) == []


def test_evaluate_boolean_neq_matches_and_message_reflects_actual_value():
    # cash_only neq false matches a listing where cash_only is actually
    # true -- the message must describe the listing's real value, not the
    # rule's threshold (which is the opposite for a neq match).
    listing = {"cash_only": 1}
    rules = [{"id": 1, "field": "cash_only", "operator": "neq", "value": "false", "enabled": 1}]
    violations = evaluate_listing(listing, rules)
    assert len(violations) == 1
    assert violations[0]["message"] == "Cash buyers only"


def test_evaluate_epc_band_worse_than_matches():
    listing = {"epc_current": "D (58)"}
    rules = [{"id": 1, "field": "epc_current", "operator": "gt", "value": "C", "enabled": 1}]
    violations = evaluate_listing(listing, rules)
    assert len(violations) == 1
    assert violations[0]["message"] == "EPC current is D (> C)"


def test_evaluate_epc_band_worse_than_does_not_match_when_better():
    listing = {"epc_current": "B (85)"}
    rules = [{"id": 1, "field": "epc_current", "operator": "gt", "value": "C", "enabled": 1}]
    assert evaluate_listing(listing, rules) == []


def test_evaluate_epc_band_eq_matches_ignoring_score():
    listing = {"epc_current": "C (69)"}
    rules = [{"id": 1, "field": "epc_current", "operator": "eq", "value": "C", "enabled": 1}]
    assert len(evaluate_listing(listing, rules)) == 1


def test_evaluate_skips_null_listing_value():
    listing = {"floor_area_sqft": None}
    rules = [{"id": 1, "field": "floor_area_sqft", "operator": "lt", "value": "700", "enabled": 1}]
    assert evaluate_listing(listing, rules) == []


def test_evaluate_skips_disabled_rule():
    listing = {"floor_area_sqft": 650}
    rules = [{"id": 1, "field": "floor_area_sqft", "operator": "lt", "value": "700", "enabled": 0}]
    assert evaluate_listing(listing, rules) == []


def test_evaluate_multiple_independent_rules():
    listing = {"floor_area_sqft": 650, "cash_only": 1, "bedrooms": 3}
    rules = [
        {"id": 1, "field": "floor_area_sqft", "operator": "lt", "value": "700", "enabled": 1},
        {"id": 2, "field": "cash_only", "operator": "eq", "value": "true", "enabled": 1},
        {"id": 3, "field": "bedrooms", "operator": "lt", "value": "2", "enabled": 1},
    ]
    violations = evaluate_listing(listing, rules)
    assert {v["rule_id"] for v in violations} == {1, 2}


# --- routes: /api/standards/rules ------------------------------------------

def test_create_rule_route(client):
    resp = client.post("/api/standards/rules", json={"field": "floor_area_sqft", "operator": "lt", "value": "700"})
    assert resp.status_code == 201
    assert resp.json()["field"] == "floor_area_sqft"


def test_create_rule_route_invalid_returns_422(client):
    resp = client.post("/api/standards/rules", json={"field": "nope", "operator": "lt", "value": "700"})
    assert resp.status_code == 422


def test_list_rules_route(client):
    client.post("/api/standards/rules", json={"field": "floor_area_sqft", "operator": "lt", "value": "700"})
    resp = client.get("/api/standards/rules")
    assert resp.status_code == 200
    assert len(resp.json()) == 1


def test_patch_rule_route(client):
    rule = client.post("/api/standards/rules", json={"field": "floor_area_sqft", "operator": "lt", "value": "700"}).json()
    resp = client.patch(f"/api/standards/rules/{rule['id']}", json={"enabled": False})
    assert resp.status_code == 200
    assert resp.json()["enabled"] == 0


def test_patch_rule_route_404(client):
    resp = client.patch("/api/standards/rules/999", json={"enabled": False})
    assert resp.status_code == 404


def test_delete_rule_route(client):
    rule = client.post("/api/standards/rules", json={"field": "floor_area_sqft", "operator": "lt", "value": "700"}).json()
    resp = client.delete(f"/api/standards/rules/{rule['id']}")
    assert resp.status_code == 204
    assert client.get("/api/standards/rules").json() == []


# --- listing detail integration --------------------------------------------

def test_get_listing_includes_standards_violations(client):
    listings_store.create_stub_listing(1, "https://www.rightmove.co.uk/properties/1")
    listings_store.apply_extracted_fields(1, {"floor_area_sqft": 650})
    client.post("/api/standards/rules", json={"field": "floor_area_sqft", "operator": "lt", "value": "700"})

    resp = client.get("/api/listings/1")
    assert resp.status_code == 200
    violations = resp.json()["standards_violations"]
    assert len(violations) == 1
    assert violations[0]["field"] == "floor_area_sqft"


def test_get_listing_no_violations_when_no_rules(client):
    listings_store.create_stub_listing(1, "https://www.rightmove.co.uk/properties/1")
    listings_store.apply_extracted_fields(1, {"floor_area_sqft": 650})

    resp = client.get("/api/listings/1")
    assert resp.json()["standards_violations"] == []
