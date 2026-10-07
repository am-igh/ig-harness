"""The Gmail helper lists up to 500 thread ids and reads only new or changed ones, so a burst of automated mail cannot push a real reply out of view."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import google_helper as gh   # noqa: E402


def test_only_new_or_changed_threads_are_read_newest_first_and_capped():
    listed = [{"id": f"t{i}", "historyId": "1"} for i in range(250)]
    assert [t["id"] for t in gh.plan_fetch(listed, {}, 100)] == [f"t{i}" for i in range(100)]
    cache = {t["id"]: {"h": "1", "t": {}} for t in listed}
    assert gh.plan_fetch(listed, cache, 100) == []
    listed[5] = {"id": "t5", "historyId": "2"}                     # a new message in an old thread
    listed.insert(0, {"id": "fresh", "historyId": "9"})            # a brand new thread, newest
    assert [t["id"] for t in gh.plan_fetch(listed, cache, 100)] == ["fresh", "t5"]


def test_the_listing_is_big_enough_to_survive_a_burst():
    assert gh.GMAIL_MAX_THREADS >= 500 and gh.GMAIL_FETCH_PER_RUN <= 100
