import os

import pytest

from app.epc_certificate import client as epc_client, store as epc_store
from app.epc_certificate.parser import CertificateParseError, parse_certificate
from app.epc_certificate.url import InvalidCertificateUrlError, canonical_certificate_url
from app.jobs import handlers, llm_enqueue, queue
from app.jobs.pipeline_status import derive_pipeline_status
from app.listings import store

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "epc_certificate_synthetic.html")
CERT_URL = "https://find-energy-certificate.service.gov.uk/energy-certificate/0000-0000-0000-0000-0000"


@pytest.fixture
def html():
    with open(FIXTURE) as f:
        return f.read()


@pytest.fixture
def listing_id(client):
    store.create_stub_listing(1, "https://www.rightmove.co.uk/properties/1")
    store.apply_extracted_fields(1, {"address": "Example Road, TOWNSVILLE", "postcode": "AB1 2CD"})
    return 1


# --- url validation ---


@pytest.mark.parametrize(
    "url",
    [
        CERT_URL,
        CERT_URL + "/",
        CERT_URL + "?print=true#renting",
        "http://find-energy-certificate.service.gov.uk/energy-certificate/0000-0000-0000-0000-0000",
        "  " + CERT_URL + "  ",
    ],
)
def test_url_is_normalised_to_canonical(url):
    assert canonical_certificate_url(url) == CERT_URL


@pytest.mark.parametrize(
    "url",
    [
        "",
        "ftp://find-energy-certificate.service.gov.uk/energy-certificate/0000-0000-0000-0000-0000",
        "https://evil.example.com/energy-certificate/0000-0000-0000-0000-0000",
        "https://find-energy-certificate.service.gov.uk.evil.com/energy-certificate/0000-0000-0000-0000-0000",
        "https://user@find-energy-certificate.service.gov.uk@evil.com/energy-certificate/0000-0000-0000-0000-0000",
        "https://find-energy-certificate.service.gov.uk/",
        "https://find-energy-certificate.service.gov.uk/energy-certificate/123",
        "https://find-energy-certificate.service.gov.uk/energy-certificate/0000-0000-0000-0000-0000/../x",
    ],
)
def test_url_rejects_non_certificate_urls(url):
    with pytest.raises(InvalidCertificateUrlError):
        canonical_certificate_url(url)


# --- parser ---


def test_parse_core_fields(html):
    d = parse_certificate(html)
    assert d["address"] == "Flat 1, 1, Example Road, TOWNSVILLE, AB1 2CD"
    assert d["postcode"] == "AB1 2CD"
    assert (d["current_rating"], d["current_score"]) == ("D", 62)
    assert (d["potential_rating"], d["potential_score"]) == ("B", 84)
    assert d["valid_until"] == "2031-03-05"
    assert d["assessment_date"] == "2021-03-04"
    assert d["certificate_date"] == "2021-03-06"
    assert d["certificate_number"] == "0000-0000-0000-0000-0000"
    assert d["assessment_type"] == "SAP"
    assert d["property_type"] == "Top-floor flat"
    assert d["total_floor_area_sqm"] == 61.5


def test_parse_energy_figures(html):
    d = parse_certificate(html)
    assert d["primary_energy_kwh_m2"] == 231
    assert d["estimated_annual_cost_gbp"] == 1234
    assert d["potential_saving_gbp"] == 310
    assert d["cost_basis_year"] == 2023
    assert d["heating_kwh_per_year"] == 9876
    assert d["hot_water_kwh_per_year"] == 2100
    assert d["co2_current_tonnes"] == 3.4
    assert d["co2_potential_tonnes"] == 1.2


def test_parse_features_keeps_na_rows(html):
    feats = parse_certificate(html)["features"]
    assert [f["feature"] for f in feats] == ["Wall", "Main heating", "Roof"]
    assert feats[0] == {
        "feature": "Wall",
        "description": "Solid brick, as built, no insulation (assumed)",
        "rating": "Poor",
    }
    assert feats[2]["rating"] == "N/A"


def test_parse_steps_including_range_cost_and_empty_potential(html):
    steps = parse_certificate(html)["steps"]
    assert steps == [
        {
            "step": 1,
            "title": "Internal or external wall insulation",
            "installation_cost": "£7,500 - £11,000",
            "yearly_saving_gbp": 240,
            "potential_rating": "78 C",
        },
        {
            "step": 2,
            "title": "Low energy lighting",
            "installation_cost": "£20",
            "yearly_saving_gbp": 70,
            "potential_rating": None,
        },
    ]


def test_parse_never_returns_assessor_personal_data(html):
    assert "Test Assessor" not in repr(parse_certificate(html))
    assert "00000 000000" not in repr(parse_certificate(html))


def test_parse_optional_sections_may_be_absent():
    minimal = (
        '<p class="epc-address">1 Road<br>AB1 2CD</p>'
        '<desc id="svg-desc">This property’s energy rating is E with a score of 40.</desc>'
    )
    d = parse_certificate(minimal)
    assert (d["current_rating"], d["current_score"]) == ("E", 40)
    assert d["potential_rating"] is None and d["features"] == [] and d["steps"] == []
    assert d["valid_until"] is None and d["heating_kwh_per_year"] is None


def test_parse_rejects_non_certificate_pages():
    with pytest.raises(CertificateParseError):
        parse_certificate("<html><body>Page not found</body></html>")
    with pytest.raises(CertificateParseError):
        parse_certificate('<p class="epc-address">1 Road<br>AB1 2CD</p>')


# --- client ---


def test_client_refuses_non_certificate_url_before_any_network_call():
    with pytest.raises(InvalidCertificateUrlError):
        epc_client.fetch_certificate_html("https://evil.example.com/energy-certificate/0000-0000-0000-0000-0000")


# --- job handler / store ---


def _job(listing_id):
    return {"id": 1, "listing_id": listing_id}


def test_handler_stores_data_and_certificate_ratings(listing_id, html, monkeypatch):
    monkeypatch.setattr(handlers.epc_client, "fetch_certificate_html", lambda url: html)
    epc_store.set_url(listing_id, CERT_URL)
    handlers.handle_epc_certificate_fetch(_job(listing_id))

    row = store.get_listing(listing_id)
    assert row["epc_current"] == "D (62)"
    assert row["epc_potential"] == "B (84)"
    assert row["epc_certificate_data"]


def test_certificate_ratings_override_manual_edits(listing_id, html, monkeypatch):
    store.apply_manual_edit(listing_id, {"epc_current": "A (95)", "epc_potential": "A (96)"})
    monkeypatch.setattr(handlers.epc_client, "fetch_certificate_html", lambda url: html)
    epc_store.set_url(listing_id, CERT_URL)
    handlers.handle_epc_certificate_fetch(_job(listing_id))
    assert store.get_listing(listing_id)["epc_current"] == "D (62)"


def test_scrape_and_llm_cannot_overwrite_certificate_ratings(listing_id, html, monkeypatch):
    monkeypatch.setattr(handlers.epc_client, "fetch_certificate_html", lambda url: html)
    epc_store.set_url(listing_id, CERT_URL)
    handlers.handle_epc_certificate_fetch(_job(listing_id))

    store.apply_extracted_fields(
        listing_id, {"epc_current": "G (5)", "epc_potential": "G (6)", "epc_source": "llm", "garden": 1}
    )
    row = store.get_listing(listing_id)
    assert (row["epc_current"], row["epc_potential"], row["epc_source"]) == ("D (62)", "B (84)", None)
    assert row["garden"] == 1  # unrelated fields still written


def test_epc_vision_not_enqueued_while_certificate_attached(listing_id):
    assert llm_enqueue.should_enqueue(listing_id, "epc_vision") is True
    epc_store.set_url(listing_id, CERT_URL)
    assert llm_enqueue.should_enqueue(listing_id, "epc_vision") is False


def test_result_dropped_if_url_replaced_mid_flight(listing_id, html, monkeypatch):
    other = CERT_URL.replace("0000-0000-0000-0000-0000", "1111-1111-1111-1111-1111")

    def fetch_then_user_replaces_url(url):
        epc_store.set_url(listing_id, other)
        return html

    monkeypatch.setattr(handlers.epc_client, "fetch_certificate_html", fetch_then_user_replaces_url)
    epc_store.set_url(listing_id, CERT_URL)
    handlers.handle_epc_certificate_fetch(_job(listing_id))

    row = store.get_listing(listing_id)
    assert row["epc_certificate_url"] == other
    assert row["epc_certificate_data"] is None
    assert row["epc_current"] is None


def test_handler_is_noop_when_url_removed(listing_id, monkeypatch):
    def boom(url):
        raise AssertionError("must not fetch")

    monkeypatch.setattr(handlers.epc_client, "fetch_certificate_html", boom)
    handlers.handle_epc_certificate_fetch(_job(listing_id))


def test_fetch_error_propagates_so_job_fails(listing_id, monkeypatch):
    def fail(url):
        raise epc_client.CertificateFetchError("certificate not found (404) -- check the URL")

    monkeypatch.setattr(handlers.epc_client, "fetch_certificate_html", fail)
    epc_store.set_url(listing_id, CERT_URL)
    with pytest.raises(epc_client.CertificateFetchError):
        handlers.handle_epc_certificate_fetch(_job(listing_id))


def test_job_type_is_registered_and_allowed_by_jobs_table(listing_id):
    assert handlers.HANDLERS["epc_certificate_fetch"] is handlers.handle_epc_certificate_fetch
    queue.enqueue_job(listing_id, "epc_certificate_fetch", "http")  # would raise on a CHECK violation


def test_pipeline_status_reflects_certificate_job():
    done = {"rightmove_extract": "done", "media_download": "done"}
    assert derive_pipeline_status({**done, "epc_certificate_fetch": "failed"}) == "failed"
    assert derive_pipeline_status({**done, "epc_certificate_fetch": "queued"}) == "processing"
    assert derive_pipeline_status({**done, "epc_certificate_fetch": "done"}) is None


def test_delete_listing_works_with_certificate_attached(listing_id, html, monkeypatch):
    monkeypatch.setattr(handlers.epc_client, "fetch_certificate_html", lambda url: html)
    epc_store.set_url(listing_id, CERT_URL)
    queue.enqueue_job(listing_id, "epc_certificate_fetch", "http")
    handlers.handle_epc_certificate_fetch(_job(listing_id))
    store.delete_listing(listing_id)
    assert store.get_listing(listing_id) is None


# --- routes ---


def test_put_rejects_invalid_url(client, listing_id):
    r = client.put(f"/api/listings/{listing_id}/epc-certificate", json={"url": "https://evil.example.com/x"})
    assert r.status_code == 422
    assert store.get_listing(listing_id)["epc_certificate_url"] is None


def test_put_404_for_unknown_listing(client):
    r = client.put("/api/listings/999/epc-certificate", json={"url": CERT_URL})
    assert r.status_code == 404


def test_put_stores_canonical_url_and_enqueues_job(client, listing_id):
    r = client.put(f"/api/listings/{listing_id}/epc-certificate", json={"url": CERT_URL + "?print=true"})
    assert r.status_code == 202
    body = r.json()
    assert body["epc_certificate_url"] == CERT_URL
    assert body["epc_certificate"] is None  # not fetched yet
    assert any(j["job_type"] == "epc_certificate_fetch" for j in queue.get_jobs_for_listing(listing_id))


def test_detail_exposes_certificate_address_and_hides_raw_column(client, listing_id, html, monkeypatch):
    monkeypatch.setattr(handlers.epc_client, "fetch_certificate_html", lambda url: html)
    client.put(f"/api/listings/{listing_id}/epc-certificate", json={"url": CERT_URL})
    handlers.handle_epc_certificate_fetch(_job(listing_id))

    body = client.get(f"/api/listings/{listing_id}").json()
    assert body["address"] == "Example Road, TOWNSVILLE"  # Rightmove's kept
    assert body["display_address"] == "Flat 1, 1, Example Road, TOWNSVILLE, AB1 2CD"
    assert "epc_certificate_data" not in body
    assert body["epc_certificate"]["postcode_mismatch"] is False
    assert body["epc_certificate"]["features"][0]["feature"] == "Wall"
    assert body["epc_source"] == "certificate"


def test_postcode_mismatch_flag_ignores_spacing_and_case(client, listing_id, html, monkeypatch):
    monkeypatch.setattr(handlers.epc_client, "fetch_certificate_html", lambda url: html)
    client.put(f"/api/listings/{listing_id}/epc-certificate", json={"url": CERT_URL})
    handlers.handle_epc_certificate_fetch(_job(listing_id))

    store.apply_extracted_fields(listing_id, {"postcode": "ab12cd"})
    assert client.get(f"/api/listings/{listing_id}").json()["epc_certificate"]["postcode_mismatch"] is False
    store.apply_extracted_fields(listing_id, {"postcode": "ZZ9 9ZZ"}, from_scrape=False)
    assert client.get(f"/api/listings/{listing_id}").json()["epc_certificate"]["postcode_mismatch"] is True
    store.apply_extracted_fields(listing_id, {"postcode": None}, from_scrape=False)
    assert client.get(f"/api/listings/{listing_id}").json()["epc_certificate"]["postcode_mismatch"] is False


def test_display_address_falls_back_to_rightmove_without_certificate(client, listing_id):
    assert client.get(f"/api/listings/{listing_id}").json()["display_address"] == "Example Road, TOWNSVILLE"


def test_patch_blocks_epc_edit_while_certificate_attached_but_not_other_fields(client, listing_id):
    client.put(f"/api/listings/{listing_id}/epc-certificate", json={"url": CERT_URL})
    r = client.patch(f"/api/listings/{listing_id}", json={"fields": {"epc_current": "A (99)"}})
    assert r.status_code == 422
    r = client.patch(f"/api/listings/{listing_id}", json={"fields": {"bedrooms": 3}})
    assert r.status_code == 200


def test_delete_certificate_detaches_and_unlocks_edits(client, listing_id, html, monkeypatch):
    monkeypatch.setattr(handlers.epc_client, "fetch_certificate_html", lambda url: html)
    client.put(f"/api/listings/{listing_id}/epc-certificate", json={"url": CERT_URL})
    handlers.handle_epc_certificate_fetch(_job(listing_id))

    r = client.delete(f"/api/listings/{listing_id}/epc-certificate")
    assert r.status_code == 200
    body = r.json()
    assert body["epc_certificate_url"] is None and body["epc_certificate"] is None
    assert body["display_address"] == "Example Road, TOWNSVILLE"
    assert body["epc_current"] == "D (62)"  # last values kept
    assert body["epc_source"] is None  # but no longer labelled as certificate
    assert body["pipeline_status"] is None  # fetch-job history cleared
    r = client.patch(f"/api/listings/{listing_id}", json={"fields": {"epc_current": "C (70)"}})
    assert r.status_code == 200


def test_list_endpoint_omits_parsed_certificate_but_has_display_address(client, listing_id, html, monkeypatch):
    monkeypatch.setattr(handlers.epc_client, "fetch_certificate_html", lambda url: html)
    client.put(f"/api/listings/{listing_id}/epc-certificate", json={"url": CERT_URL})
    handlers.handle_epc_certificate_fetch(_job(listing_id))

    item = client.get("/api/listings").json()[0]
    assert "epc_certificate" not in item and "epc_certificate_data" not in item
    assert item["display_address"] == "Flat 1, 1, Example Road, TOWNSVILLE, AB1 2CD"


# --- review follow-ups ---


@pytest.mark.parametrize(
    "url",
    [
        "https://[find-energy-certificate.service.gov.uk/energy-certificate/0000-0000-0000-0000-0000",
        "https://find-energy-certificate.service.gov.uk/energy-certificate/٠٠٠٠-0000-0000-0000-0000",
    ],
)
def test_url_malformed_or_non_ascii_digits_rejected_cleanly(url):
    with pytest.raises(InvalidCertificateUrlError):
        canonical_certificate_url(url)


def test_url_port_and_uppercase_host_normalised():
    got = canonical_certificate_url(
        "https://FIND-ENERGY-CERTIFICATE.service.gov.uk:8443/energy-certificate/0000-0000-0000-0000-0000"
    )
    assert got == CERT_URL


def test_put_malformed_url_is_422_not_500(client, listing_id):
    r = client.put(f"/api/listings/{listing_id}/epc-certificate", json={"url": "https://[bad"})
    assert r.status_code == 422


def test_replace_after_success_drops_certificate_source_label(client, listing_id, html, monkeypatch):
    monkeypatch.setattr(handlers.epc_client, "fetch_certificate_html", lambda url: html)
    client.put(f"/api/listings/{listing_id}/epc-certificate", json={"url": CERT_URL})
    handlers.handle_epc_certificate_fetch(_job(listing_id))

    other = CERT_URL.replace("0000-0000-0000-0000-0000", "1111-1111-1111-1111-1111")
    body = client.put(f"/api/listings/{listing_id}/epc-certificate", json={"url": other}).json()
    assert body["epc_certificate"] is None and body["epc_source"] is None

    body = client.delete(f"/api/listings/{listing_id}/epc-certificate").json()
    assert body["epc_source"] is None  # not a stale llm/rightmove claim on cert-derived ratings


def test_pending_attach_keeps_existing_source_label(client, listing_id):
    store.apply_extracted_fields(listing_id, {"epc_current": "C (70)", "epc_source": "llm"})
    client.put(f"/api/listings/{listing_id}/epc-certificate", json={"url": CERT_URL})
    assert client.get(f"/api/listings/{listing_id}").json()["epc_source"] == "llm"


def test_postcode_mismatch_skipped_for_partial_postcode(client, listing_id, html, monkeypatch):
    monkeypatch.setattr(handlers.epc_client, "fetch_certificate_html", lambda url: html)
    client.put(f"/api/listings/{listing_id}/epc-certificate", json={"url": CERT_URL})
    handlers.handle_epc_certificate_fetch(_job(listing_id))
    store.apply_extracted_fields(listing_id, {"postcode": "ZZ9"}, from_scrape=False)
    assert client.get(f"/api/listings/{listing_id}").json()["epc_certificate"]["postcode_mismatch"] is False


def test_save_parsed_without_potential_rating_leaves_potential_null(listing_id, html):
    from app.epc_certificate.parser import parse_certificate

    data = parse_certificate(html)
    data["potential_rating"] = None
    data["potential_score"] = None
    epc_store.set_url(listing_id, CERT_URL)
    assert epc_store.save_parsed(listing_id, CERT_URL, data) is True
    row = store.get_listing(listing_id)
    assert row["epc_current"] == "D (62)" and row["epc_potential"] is None


def test_worker_retry_path_for_parse_error(listing_id, monkeypatch):
    monkeypatch.setattr(handlers.epc_client, "fetch_certificate_html", lambda url: "<html>Page not found</html>")
    epc_store.set_url(listing_id, CERT_URL)
    job_id = queue.enqueue_job(listing_id, "epc_certificate_fetch", "http")
    job = queue.claim_next_job("http")
    assert job["id"] == job_id
    with pytest.raises(Exception) as exc:
        handlers.HANDLERS[job["job_type"]](job)
    queue.fail_job(job_id, str(exc.value))
    row = [j for j in queue.get_jobs_for_listing(listing_id) if j["id"] == job_id][0]
    assert row["status"] == "queued" and row["attempts"] == 1  # retried, not permanently failed yet


def test_migration_0038_preserves_existing_jobs_rows(tmp_path, monkeypatch):
    import shutil
    import sqlite3

    from app.db import migrate

    src = migrate.MIGRATIONS_DIR
    old_dir = tmp_path / "old"
    old_dir.mkdir()
    for _, name in migrate._migration_files():
        if int(name[:4]) < 38:
            shutil.copy(os.path.join(src, name), old_dir / name)

    db = str(tmp_path / "upgrade.db")
    monkeypatch.setenv("ROOST_DB_PATH", db)
    monkeypatch.setattr(migrate, "MIGRATIONS_DIR", str(old_dir))
    migrate.run_migrations()

    conn = sqlite3.connect(db)
    now = "2026-01-01T00:00:00"
    conn.execute("INSERT INTO listings (id, url, created_at, updated_at) VALUES (1, 'u', ?, ?)", (now, now))
    conn.execute(
        "INSERT INTO jobs (id, listing_id, job_type, lane, status, created_at, updated_at) "
        "VALUES (1, 1, 'rightmove_extract', 'http', 'done', ?, ?)",
        (now, now),
    )
    conn.execute(
        "INSERT INTO jobs (id, listing_id, job_type, lane, status, depends_on_job_id, attempts, last_error, "
        "created_at, updated_at, skip_llm_chain) VALUES (2, 1, 'media_download', 'http', 'failed', 1, 3, 'boom', ?, ?, 1)",
        (now, now),
    )
    conn.commit()
    conn.close()

    monkeypatch.setattr(migrate, "MIGRATIONS_DIR", src)
    migrate.run_migrations()

    conn = sqlite3.connect(db)
    rows = conn.execute(
        "SELECT id, job_type, status, depends_on_job_id, attempts, last_error, skip_llm_chain FROM jobs ORDER BY id"
    ).fetchall()
    assert rows == [
        (1, "rightmove_extract", "done", None, 0, None, 0),
        (2, "media_download", "failed", 1, 3, "boom", 1),
    ]
    conn.execute(
        "INSERT INTO jobs (listing_id, job_type, lane, status, created_at, updated_at) "
        "VALUES (1, 'epc_certificate_fetch', 'http', 'queued', ?, ?)",
        (now, now),
    )
    conn.execute("SELECT epc_certificate_url, epc_certificate_data FROM listings")
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] in (0, 1)
    conn.close()
