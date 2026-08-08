import os

import pytest

from app.listings import store


@pytest.fixture
def listing_id(client, media_dir):
    store.create_stub_listing(1, "https://www.rightmove.co.uk/properties/1")
    return 1


def test_list_media_404_for_unknown_listing(client, media_dir):
    resp = client.get("/api/listings/999/media")
    assert resp.status_code == 404


def test_list_media_empty_when_no_files(client, listing_id):
    resp = client.get(f"/api/listings/{listing_id}/media")
    assert resp.status_code == 200
    assert resp.json() == {"photos": [], "floorplans": [], "epc": []}


def test_list_media_returns_files(client, listing_id, media_dir):
    photos_dir = os.path.join(media_dir, str(listing_id), "photos")
    os.makedirs(photos_dir)
    with open(os.path.join(photos_dir, "01.jpeg"), "wb") as f:
        f.write(b"fake image bytes")

    resp = client.get(f"/api/listings/{listing_id}/media")
    assert resp.json()["photos"] == ["01.jpeg"]


def test_get_media_file_404_for_unknown_listing(client, media_dir):
    resp = client.get("/api/listings/999/media/photos/01.jpeg")
    assert resp.status_code == 404


def test_get_media_file_404_for_unknown_category(client, listing_id):
    resp = client.get(f"/api/listings/{listing_id}/media/floorplan-secrets/01.jpeg")
    assert resp.status_code == 404


@pytest.mark.parametrize(
    "filename",
    ["../../etc/passwd", "..%2Fsecret", "/etc/passwd", "sub/dir.jpeg", "bad name!.jpeg"],
)
def test_get_media_file_rejects_unsafe_filenames(client, listing_id, filename):
    resp = client.get(f"/api/listings/{listing_id}/media/photos/{filename}")
    assert resp.status_code in (400, 404)


def test_get_media_file_returns_existing_file(client, listing_id, media_dir):
    photos_dir = os.path.join(media_dir, str(listing_id), "photos")
    os.makedirs(photos_dir)
    with open(os.path.join(photos_dir, "01.jpeg"), "wb") as f:
        f.write(b"fake image bytes")

    resp = client.get(f"/api/listings/{listing_id}/media/photos/01.jpeg")
    assert resp.status_code == 200
    assert resp.content == b"fake image bytes"


def test_get_media_file_404_for_missing_file(client, listing_id, media_dir):
    os.makedirs(os.path.join(media_dir, str(listing_id), "photos"))
    resp = client.get(f"/api/listings/{listing_id}/media/photos/nope.jpeg")
    assert resp.status_code == 404


def test_get_media_file_blocks_symlink_escape(client, listing_id, media_dir, tmp_path):
    photos_dir = os.path.join(media_dir, str(listing_id), "photos")
    os.makedirs(photos_dir)
    secret = tmp_path / "outside_secret.txt"
    secret.write_text("top secret")
    os.symlink(secret, os.path.join(photos_dir, "escape.txt"))

    resp = client.get(f"/api/listings/{listing_id}/media/photos/escape.txt")
    assert resp.status_code == 404
