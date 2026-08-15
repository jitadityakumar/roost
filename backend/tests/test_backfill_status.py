from app.destinations import backfill_status

# conftest.py's autouse isolated_db fixture clears backfill_status._runs
# before every test (same process-wide-state reasoning as the DB reset), so
# these tests don't need their own reset fixture.


def test_get_returns_none_for_untracked_destination():
    assert backfill_status.get(123) is None


def test_start_then_get_reports_running_with_zero_done():
    backfill_status.start(1, total=5)
    assert backfill_status.get(1) == {"status": "running", "done": 0, "total": 5}


def test_increment_advances_done_count():
    backfill_status.start(1, total=3)
    backfill_status.increment(1)
    backfill_status.increment(1)
    assert backfill_status.get(1)["done"] == 2


def test_finish_sets_terminal_status():
    backfill_status.start(1, total=1)
    backfill_status.increment(1)
    backfill_status.finish(1, "done")
    assert backfill_status.get(1) == {"status": "done", "done": 1, "total": 1}


def test_start_returns_false_and_does_not_reset_an_in_flight_run():
    assert backfill_status.start(1, total=10) is True
    backfill_status.increment(1)
    assert backfill_status.start(1, total=99) is False
    assert backfill_status.get(1) == {"status": "running", "done": 1, "total": 10}


def test_start_after_a_previous_run_finished_starts_a_fresh_run():
    backfill_status.start(1, total=5)
    backfill_status.finish(1, "done")
    assert backfill_status.start(1, total=2) is True
    assert backfill_status.get(1) == {"status": "running", "done": 0, "total": 2}


def test_increment_and_finish_are_no_ops_for_an_untracked_destination():
    backfill_status.increment(999)
    backfill_status.finish(999, "done")
    assert backfill_status.get(999) is None


def test_runs_for_different_destinations_are_independent():
    backfill_status.start(1, total=5)
    backfill_status.start(2, total=10)
    backfill_status.increment(1)
    assert backfill_status.get(1)["done"] == 1
    assert backfill_status.get(2)["done"] == 0
