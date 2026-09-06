from app.comments import store
from app.listings import store as listings_store


def _listing(id_=1):
    listings_store.create_stub_listing(id_, f"https://www.rightmove.co.uk/properties/{id_}")


def test_create_comment_returns_the_created_row():
    _listing()
    row = store.create_comment(1, "general", "Nice garden", "JK")
    assert row["listing_id"] == 1
    assert row["comment_type"] == "general"
    assert row["text"] == "Nice garden"
    assert row["initials"] == "JK"
    assert row["created_at"] is not None
    assert row["updated_at"] == row["created_at"]


def test_list_comments_orders_most_recent_first():
    _listing()
    first = store.create_comment(1, "general", "First", "JK")
    second = store.create_comment(1, "general", "Second", "JK")
    rows = store.list_comments(1)
    assert [r["id"] for r in rows] == [second["id"], first["id"]]


def test_list_comments_scoped_to_listing():
    _listing(1)
    _listing(2)
    store.create_comment(1, "general", "For listing 1", "JK")
    store.create_comment(2, "general", "For listing 2", "JK")
    rows = store.list_comments(1)
    assert len(rows) == 1
    assert rows[0]["text"] == "For listing 1"


def test_get_comment_returns_none_for_missing_id():
    assert store.get_comment(999) is None


def test_update_comment_changes_text_and_initials_not_created_at():
    _listing()
    created = store.create_comment(1, "general", "Original", "JK")
    updated = store.update_comment(created["id"], "Edited", "AB")
    assert updated["text"] == "Edited"
    assert updated["initials"] == "AB"
    assert updated["created_at"] == created["created_at"]
    assert updated["comment_type"] == "general"


def test_update_comment_returns_none_for_missing_id():
    assert store.update_comment(999, "text", "JK") is None


def test_delete_comment_removes_it():
    _listing()
    created = store.create_comment(1, "general", "Bye", "JK")
    store.delete_comment(created["id"])
    assert store.get_comment(created["id"]) is None


def test_backfilled_rows_sort_after_real_rows_via_id_tiebreak():
    # Backfilled rows (created_at=NULL) sort after real (non-null) rows
    # under `ORDER BY created_at DESC` regardless of id -- SQLite always
    # sorts NULLs last under DESC.
    _listing()
    store.create_comment(1, "general", "Backfilled", None)
    real = store.create_comment(1, "general", "Real", "JK")
    from app.db.connection import get_connection

    conn = get_connection()
    conn.execute("UPDATE comments SET created_at = NULL, updated_at = NULL WHERE text = 'Backfilled'")
    conn.commit()
    conn.close()

    rows = store.list_comments(1)
    assert rows[0]["id"] == real["id"]
    assert rows[1]["text"] == "Backfilled"
