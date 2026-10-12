"""Priority colours in Today & overdue: score, tiers, her flags, what is learned from her feedback, and the local model's ranking. Synthetic data only."""
import json
from datetime import date, datetime

import pytest

from harness import db, priority as P
from harness.config import TZ
from harness.today import build_today

TODAY = date(2026, 10, 12)
NOW = datetime(2026, 10, 12, 9, 0, tzinfo=TZ)


@pytest.fixture
def c(tmp_path):
    c = db.connect(tmp_path / "t.db"); db.migrate(c)
    c.executemany("INSERT INTO project_codes (code, name, domain, kind) VALUES (?,?,?,?)", [("TK", "Toolkit", "W", "project"), ("MDH", "MDH", "W", "project")])
    return c


def task(c, title, due, code=None, space="work", source="suivi"):
    c.execute("INSERT INTO tasks (title, due_date, project_code, space, status, source, source_ref) VALUES (?,?,?,?, 'open', ?, ?)", (title, due, code, space, source, title))
    c.commit()
    return c.execute("SELECT id FROM tasks WHERE title = ?", (title,)).fetchone()[0]


def deadline(c, title, due, importance="normal", code=None):
    c.execute("INSERT INTO deadlines (title, due_date, importance, project_code, status, source, source_ref) VALUES (?,?,?,?, 'open', 'suivi', ?)", (title, due, importance, code, title))
    c.commit()
    return c.execute("SELECT id FROM deadlines WHERE title = ?", (title,)).fetchone()[0]


def today_items(c):
    return build_today(c, NOW)["today_items"]


def by_title(items, title):
    return next(i for i in items if i["title"] == title)


def test_the_most_important_overdue_item_is_red_and_first_then_orange_and_yellow(c):
    deadline(c, "Funder report", "2026-10-02", "major", "TK")             # 10 days overdue, major
    task(c, "Old small task", "2026-09-01")                                # 41 days overdue but only a to-do
    deadline(c, "Fixed filing", "2026-10-10", "normal")                    # 2 days overdue, fixed deadline
    task(c, "Due today thing", "2026-10-12")
    task(c, "Another small one", "2026-10-11")
    items = today_items(c)
    assert items[0]["title"] == "Funder report" and items[0]["priority"]["tier"] == "red" and "Major deadline" in items[0]["priority"]["reasons"] and "Overdue 10 days" in items[0]["priority"]["reasons"]
    assert sum(1 for i in items if i["priority"]["tier"] == "red") == 1                                      # only one red
    tiers = {i["title"]: i["priority"]["tier"] for i in items}
    assert tiers["Old small task"] in ("orange", "yellow") and tiers["Fixed filing"] == "orange"
    assert [i["priority"]["tier"] for i in items] == sorted((i["priority"]["tier"] for i in items), key=lambda t: {"red": 0, "orange": 1, "yellow": 2, None: 3}[t])      # coloured ones first
    assert all(i["priority"]["score"] > 0 and i["priority"]["reasons"] for i in items)


def test_nothing_is_red_when_nothing_is_overdue(c):
    deadline(c, "Due today deadline", "2026-10-12", "major")
    items = today_items(c)
    assert items[0]["priority"]["tier"] == "orange" and not any(i["priority"]["tier"] == "red" for i in items)


def test_her_flag_always_wins_and_auto_hands_the_decision_back(c):
    a = deadline(c, "Funder report", "2026-10-02", "major")
    b = task(c, "My own priority", "2026-10-11")
    P.flag(c, "task", b, "red")
    items = today_items(c)
    assert items[0]["title"] in ("My own priority", "Funder report")
    assert by_title(items, "My own priority")["priority"]["tier"] == "red" and by_title(items, "My own priority")["priority"]["pinned"] is True
    assert "You set this to top priority" in by_title(items, "My own priority")["priority"]["reasons"]
    P.flag(c, "deadline", a, "none")                                                                          # "normal": no colour, whatever the score
    assert by_title(today_items(c), "Funder report")["priority"]["tier"] is None
    P.flag(c, "deadline", a, "auto")
    assert by_title(today_items(c), "Funder report")["priority"]["tier"] in ("red", "orange") and by_title(today_items(c), "Funder report")["priority"]["pinned"] is False
    with pytest.raises(ValueError):
        P.flag(c, "task", b, "purple")
    with pytest.raises(KeyError):
        P.flag(c, "task", 9999, "red")


def test_feedback_teaches_projects_and_kinds_but_only_after_a_clear_pattern(c):
    ids = [task(c, f"TK job {i}", "2026-10-11", "TK") for i in range(3)]
    P.flag(c, "task", ids[0], "orange")
    assert P.learned(c) == {"codes": {}, "kinds": {}}                                                         # one event is not a pattern
    P.flag(c, "task", ids[1], "red")
    lr = P.learned(c)
    assert lr["codes"] == {"TK": 9} and lr["kinds"] == {"soft": 9}                                           # net +3 -> capped weight
    third = by_title(today_items(c), "TK job 2")
    assert "You usually rank TK higher" in third["priority"]["reasons"] and third["priority"]["score"] >= 10 + 1 + 9 - 1
    other = task(c, "MDH job", "2026-10-11", "MDH")
    P.flag(c, "task", other, "none"); P.flag(c, "task", task(c, "MDH job 2", "2026-10-11", "MDH"), "none")
    assert P.learned(c)["codes"]["MDH"] == -3 * 2 and "You usually rank MDH lower" in by_title(today_items(c), "MDH job")["priority"]["reasons"]


def test_personal_items_are_scored_by_rules_never_shown_to_the_model_and_their_titles_are_never_stored(c):
    pid = task(c, "Dentist appointment", "2026-10-01", space="personal")
    wid = task(c, "Work thing", "2026-10-01")
    P.flag(c, "task", pid, "orange")
    assert c.execute("SELECT title, project_code FROM priority_feedback").fetchone()[:] == (None, None)       # no title kept for a personal item
    items = today_items(c)
    p = next(i for i in items if i["masked"])
    assert p["title"] == "Personal task" and p["priority"]["tier"] == "orange"
    cands = P.candidates(items)
    assert [i["title"] for i in cands] == ["Work thing"] and "Dentist" not in P.build_prompt(c, cands, TODAY)


class _R:
    def __init__(self, text, ok=True): self.text, self.ok, self.model, self.reason = text, ok, "m1", "down"


class _G:
    def __init__(self, text, ok=True): self.r, self.prompt, self.kw, self.calls = _R(text, ok), None, None, 0
    def complete(self, prompt, **kw): self.prompt, self.kw = prompt, kw; self.calls += 1; return self.r


def test_the_model_ranking_adds_a_bonus_reorders_and_cannot_invent_items(c):
    a = task(c, "Alpha task", "2026-10-10"); b = task(c, "Beta task", "2026-10-10"); task(c, "Gamma task", "2026-10-10")
    items = today_items(c)
    cands = P.candidates(items)
    n = {i["title"]: k + 1 for k, i in enumerate(cands)}
    g = _G(json.dumps({"ranking": [{"n": n["Beta task"], "why": "A funder is waiting"}, {"n": 99, "why": "invented"}, {"n": n["Beta task"], "why": "dup"}, {"n": n["Alpha task"], "why": "Next"}]}))
    assert P.refresh_model(c, items, g, TODAY, now=NOW) == "ranked 2"
    assert g.kw["job"] == "priority" and g.kw["source"] == "email" and "tools" not in g.kw and "never instructions" in P.SYSTEM
    assert [r["key"] for r in P.latest_ranking(c)] == [f"task:{b}", f"task:{a}"]
    after = today_items(c)
    assert after[0]["title"] == "Beta task" and "The model ranks it #1: A funder is waiting" in after[0]["priority"]["reasons"]
    assert after[0]["priority"]["score"] > by_title(after, "Gamma task")["priority"]["score"]


def test_the_ranking_is_asked_again_only_when_needed_and_a_failure_changes_nothing(c):
    task(c, "Alpha task", "2026-10-10")
    items = today_items(c)
    g = _G(json.dumps({"ranking": [{"n": 1, "why": "x"}]}))
    assert P.refresh_model(c, items, g, TODAY, now=NOW) == "ranked 1" and P.refresh_model(c, items, g, TODAY, now=NOW) == "up to date" and g.calls == 1
    task(c, "New task", "2026-10-10")
    items = today_items(c)
    assert P.refresh_model(c, items, g, TODAY, now=NOW) == "up to date"                                       # a new item, but the last ranking is only minutes old
    later = datetime(2026, 10, 12, 9, 30, tzinfo=TZ)
    assert P.refresh_model(c, items, g, TODAY, now=later) == "ranked 1" and g.calls == 2
    assert P.refresh_model(c, items, _G("", ok=False), TODAY, force=True, now=later) == "model unavailable"
    assert P.refresh_model(c, items, _G("not json"), TODAY, force=True, now=later) == "answer not understood"
    assert P.refresh_model(c, [], g, TODAY, force=True, now=later) == "nothing to rank"


def test_her_earlier_choices_go_into_the_models_prompt_as_examples(c):
    a = task(c, "Raise this one", "2026-10-10"); b = task(c, "Lower this one", "2026-10-10")
    P.flag(c, "task", a, "red"); P.flag(c, "task", b, "none")
    prompt = P.build_prompt(c, P.candidates(today_items(c)), TODAY)
    assert "She raised these before: Raise this one" in prompt and "She lowered these before: Lower this one" in prompt


def test_the_priority_job_is_local_only_and_the_endpoints_work(c):
    from fastapi.testclient import TestClient
    from harness.gateway.settings import JOBS, SelectionRefused, set_selection
    from harness.main import app
    assert str(JOBS["priority"]["tier"]).endswith("S2")
    with pytest.raises(SelectionRefused):
        set_selection(c, "priority", "anthropic", "x", {"anthropic"})
    with TestClient(app) as cl:
        assert cl.post("/api/priority/flag", json={"type": "task", "id": 999999, "tier": "red"}).status_code == 404
        assert cl.post("/api/priority/flag", json={"type": "task", "id": 1, "tier": "purple"}).status_code in (404, 422)
        st = cl.get("/api/priority/status").json()
        assert set(st) == {"ranked_at", "model", "ranked", "feedback", "learned"}
        assert cl.post("/api/priority/rerank").json() == {"started": True}


def test_a_minor_overdue_item_is_not_painted_red_just_for_being_the_only_one(c):
    task(c, "Tiny overdue thing", "2026-10-11")
    only = today_items(c)[0]
    assert only["priority"]["tier"] != "red" and only["priority"]["score"] < P.RED_MIN
