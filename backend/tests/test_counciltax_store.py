from app.counciltax import store
from app.listings import store as listings_store


def _listing(id_, postcode="SM1 2AB", gss="E00000001", district="Sampleton", band=None):
    listings_store.create_stub_listing(id_, f"https://www.rightmove.co.uk/properties/{id_}")
    fields = {"postcode": postcode, "admin_district": district, "admin_district_gss": gss}
    if band is not None:
        fields["council_tax_band"] = band
    listings_store.apply_extracted_fields(id_, fields)


def test_list_councils_shows_a_listing_only_council_as_needing_rates():
    _listing(1)
    councils = store.list_councils()
    assert len(councils) == 1
    assert councils[0]["gss_code"] == "E00000001"
    assert councils[0]["council_name"] == "Sampleton"
    assert councils[0]["band_a"] is None


def test_list_councils_includes_a_rates_only_council_with_no_listings():
    store.upsert_rates("E00000099", "Rateville", {"band_a": 1000})
    councils = store.list_councils()
    assert len(councils) == 1
    assert councils[0]["gss_code"] == "E00000099"
    assert councils[0]["council_name"] == "Rateville"


def test_list_councils_merges_listing_and_rates_rows_for_the_same_council():
    _listing(1)
    store.upsert_rates("E00000001", "Sampleton Council", {"band_a": 1200})
    councils = store.list_councils()
    assert len(councils) == 1
    assert councils[0]["council_name"] == "Sampleton Council"
    assert councils[0]["band_a"] == 1200


def test_list_councils_name_falls_back_to_listing_admin_district_when_no_rate_row():
    _listing(1, district="Listing-Derived Name")
    councils = store.list_councils()
    assert councils[0]["council_name"] == "Listing-Derived Name"


def test_upsert_rates_is_a_full_replacement_not_a_merge():
    store.upsert_rates("E00000001", "Sampleton", {"band_a": 1000, "band_b": 1100})
    store.upsert_rates("E00000001", "Sampleton", {"band_a": 2000})
    row = store.list_councils()[0]
    assert row["band_a"] == 2000
    assert row["band_b"] is None  # cleared, not merged


def test_delete_council_removes_the_rates_row():
    store.upsert_rates("E00000001", "Sampleton", {"band_a": 1000})
    store.delete_council("E00000001")
    assert store.list_councils() == []


def test_monthly_estimate_with_full_data():
    store.upsert_rates("E00000001", "Sampleton", {"band_d": 2340})
    assert store.monthly_estimate("E00000001", "D") == 195


def test_monthly_estimate_none_for_missing_gss():
    assert store.monthly_estimate(None, "D") is None


def test_monthly_estimate_none_for_no_rates_row():
    assert store.monthly_estimate("E00000001", "D") is None


def test_monthly_estimate_none_for_unset_band():
    store.upsert_rates("E00000001", "Sampleton", {"band_a": 1000})
    assert store.monthly_estimate("E00000001", "D") is None


def test_monthly_estimate_normalizes_lowercase_band_letter():
    store.upsert_rates("E00000001", "Sampleton", {"band_d": 2340})
    assert store.monthly_estimate("E00000001", "d") == 195


def test_monthly_estimate_none_for_invalid_band():
    store.upsert_rates("E00000001", "Sampleton", {"band_d": 2340})
    assert store.monthly_estimate("E00000001", "I") is None
    assert store.monthly_estimate("E00000001", "TBC") is None
    # A naive .strip().upper()[:1] would truncate this to "B" and silently
    # return band B's (unset) rate instead of rejecting the garbage input.
    assert store.monthly_estimate("E00000001", "Band D") is None
    assert store.monthly_estimate("E00000001", None) is None
