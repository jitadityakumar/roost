import json

import pytest

from app.listings import store


@pytest.fixture
def listing_id():
    store.create_stub_listing(1, "https://www.rightmove.co.uk/properties/1")
    return 1


def test_apply_extracted_fields_writes_values(listing_id):
    store.apply_extracted_fields(listing_id, {"price_gbp": 500000, "address": "1 Test St"})
    listing = store.get_listing(listing_id)
    assert listing["price_gbp"] == 500000
    assert listing["address"] == "1 Test St"


def test_manual_edit_freezes_value_against_later_scrape(listing_id):
    store.apply_manual_edit(listing_id, {"price_gbp": 600000})
    store.apply_extracted_fields(listing_id, {"price_gbp": 500000})

    listing = store.get_listing(listing_id)
    assert listing["price_gbp"] == 600000
    assert "price_gbp" in json.loads(listing["edited_fields"])


def test_manual_edit_freezes_source_companion_against_later_scrape(listing_id):
    # User manually corrects council_tax_band; a later scrape must not
    # overwrite the value *or* silently relabel its source as 'rightmove'.
    store.apply_manual_edit(listing_id, {"council_tax_band": "F"})
    store.apply_extracted_fields(
        listing_id, {"council_tax_band": "D", "council_tax_band_source": "rightmove"}
    )

    listing = store.get_listing(listing_id)
    assert listing["council_tax_band"] == "F"
    assert listing["council_tax_band_source"] is None


def test_extracted_fields_not_sticky_are_overwritten(listing_id):
    store.apply_extracted_fields(listing_id, {"price_gbp": 500000})
    store.apply_extracted_fields(listing_id, {"price_gbp": 510000})

    assert store.get_listing(listing_id)["price_gbp"] == 510000


def test_apply_extracted_fields_raises_for_unknown_listing():
    with pytest.raises(ValueError):
        store.apply_extracted_fields(999, {"price_gbp": 1})


def test_apply_manual_edit_raises_for_unknown_listing():
    with pytest.raises(ValueError):
        store.apply_manual_edit(999, {"price_gbp": 1})


def test_target_fields_all_sticky_false_when_none_edited(listing_id):
    assert store.target_fields_all_sticky(listing_id, ["council_tax_band", "chain_free"]) is False


def test_target_fields_all_sticky_true_when_all_edited(listing_id):
    store.apply_manual_edit(listing_id, {"council_tax_band": "F", "chain_free": 1})
    assert store.target_fields_all_sticky(listing_id, ["council_tax_band", "chain_free"]) is True


def test_target_fields_all_sticky_false_when_only_some_edited(listing_id):
    store.apply_manual_edit(listing_id, {"council_tax_band": "F"})
    assert store.target_fields_all_sticky(listing_id, ["council_tax_band", "chain_free"]) is False


def test_target_fields_all_sticky_treats_source_companion_as_sticky(listing_id):
    # council_tax_band_source is the _source companion of council_tax_band —
    # editing the value field should make the source field read as sticky too.
    store.apply_manual_edit(listing_id, {"council_tax_band": "F"})
    assert store.target_fields_all_sticky(listing_id, ["council_tax_band_source"]) is True


def test_delete_listing_cascades(listing_id):
    from app.jobs import queue

    queue.enqueue_job(listing_id, "rightmove_extract", "http")
    store.insert_snapshot(listing_id, 500000, None, {"id": listing_id})

    store.delete_listing(listing_id)

    assert store.get_listing(listing_id) is None
    assert queue.get_jobs_for_listing(listing_id) == []
