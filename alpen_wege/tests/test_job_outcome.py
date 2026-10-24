# Local application
from app.management.jobs.outcome import GENERIC_FAILURE, interpret_result


def test_keep_and_continue():
    assert interpret_result({"status": "skipped", "job": "keep"}) == ("keep", {})
    assert interpret_result({"status": "ready", "job": "continue", "stage": "detecting_pois"}) == (
        "continue", {"stage": "detecting_pois"})


def test_failed_uses_message_or_generic_text():
    assert interpret_result({"status": "failed", "message": "Bad file"}) == ("failed", {"message": "Bad file"})
    assert interpret_result({"status": "failed", "error": "internal_error"}) == ("failed", {"message": GENERIC_FAILURE})


def test_anything_else_succeeds_and_hides_reserved_keys():
    action, info = interpret_result({"status": "skipped", "track_id": "t", "stage": "x", "message": "m"})
    assert action == "succeeded"
    assert info["result"] == {"status": "skipped", "track_id": "t"}


def test_non_dict_and_large_results():
    assert interpret_result(None) == ("succeeded", {"result": None})
    action, info = interpret_result({"status": "ok", "blob": "x" * 5000})
    assert action == "succeeded" and info["result"] == {"status": "ok"}


def test_gpx_chain_results():
    handed_over = {"track_id": "t", "status": "ready", "warnings": [], "job": "continue", "stage": "detecting_pois"}
    assert interpret_result(handed_over) == ("continue", {"stage": "detecting_pois"})
    action, info = interpret_result({"track_id": "t", "status": "ok", "visits_added": 2, "cards_added": 1})
    assert action == "succeeded" and info["result"]["visits_added"] == 2
    assert interpret_result({"track_id": "t", "status": "skipped", "job": "keep"}) == ("keep", {})
    action, info = interpret_result({"track_id": "t", "status": "skipped", "reason": "archived"})
    assert action == "succeeded" and info["result"]["reason"] == "archived"
