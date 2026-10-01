"""IG Harness API. Phase 1 skeleton: health check only."""
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException

from harness import db, deadlines, today as today_view
from harness.config import DATA_DIR, VERSION
from harness.importers.run import run_all


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create or upgrade the database when the API starts.
    conn = db.connect()
    db.migrate(conn)
    conn.close()
    yield


app = FastAPI(title="IG Harness", version=VERSION, lifespan=lifespan)


@app.get("/api/health")
def health() -> dict:
    conn = db.connect()
    schema = db.schema_version(conn)
    conn.close()
    return {
        "schema_version": schema,
        "status": "ok",
        "version": VERSION,
        "data_dir_mounted": DATA_DIR.is_dir(),
    }


@app.post("/api/import")
def import_now() -> dict:
    """Re-read Suivi.xlsx and Registre_Projets.xlsx (read-only) and report what changed."""
    return {"reports": run_all()}


def _with_conn(fn):
    conn = db.connect()
    try:
        return fn(conn)
    finally:
        conn.close()


@app.get("/api/today")
def get_today() -> dict:
    return _with_conn(today_view.build_today)


@app.get("/api/done/week")
def get_done_week() -> dict:
    from harness.config import now_local
    return {"items": _with_conn(lambda c: today_view.done_list(c, now_local().date()))}


@app.get("/api/deadlines/{deadline_id}")
def get_deadline(deadline_id: int) -> dict:
    from harness.config import now_local
    d = _with_conn(lambda c: today_view.deadline_detail(c, deadline_id, now_local().date()))
    if d is None:
        raise HTTPException(404, "No such deadline")
    return d


@app.post("/api/items/{item_type}/{item_id}/done")
def tick(item_type: str, item_id: int) -> dict:
    if item_type not in deadlines.ITEM_TYPES:
        raise HTTPException(404, "Unknown item type")
    return {"changed": _with_conn(lambda c: deadlines.mark_done(c, item_type, item_id))}


@app.post("/api/items/{item_type}/{item_id}/undo")
def untick(item_type: str, item_id: int) -> dict:
    if item_type not in deadlines.ITEM_TYPES:
        raise HTTPException(404, "Unknown item type")
    return {"changed": _with_conn(lambda c: deadlines.mark_undone(c, item_type, item_id))}


@app.get("/api/gateway/status")
def gateway_status() -> dict:
    """Is the local model reachable, and where does the external-spend budget stand."""
    from harness.gateway import budget
    from harness.gateway.providers import OllamaProvider
    local = OllamaProvider().status()
    conn = db.connect()
    try:
        spend, state = budget.month_spend(conn), budget.state(conn)
    finally:
        conn.close()
    return {"local": local, "external_spend_chf": round(spend, 2), "budget_state": state}


@app.get("/api/privacy-log")
def privacy_log(limit: int = 50) -> dict:
    rows = _with_conn(lambda c: [dict(r) for r in c.execute(
        "SELECT ts, provider, model, tier, redacted, in_chars, out_chars, cost_chf, purpose, outcome, detail "
        "FROM privacy_log ORDER BY id DESC LIMIT ?", (min(limit, 500),))])
    return {"items": rows}


# --- Email triage (runs on demand; the local model can take a while, so it runs in the background) ---
_triage = {"running": False, "last": None, "finished_at": None}
_triage_lock = threading.Lock()


def _run_triage() -> None:
    from harness import triage
    from harness.config import now_local
    conn = db.connect()
    try:
        result = triage.triage_pending(conn)
    except Exception as e:  # never crash the API thread
        result = {"error": f"{type(e).__name__}: {e}"}
    finally:
        conn.close()
        with _triage_lock:
            _triage.update(running=False, last=result, finished_at=now_local().isoformat(timespec="seconds"))


@app.post("/api/triage/run")
def triage_run(redo: bool = False) -> dict:
    with _triage_lock:
        if _triage["running"]:
            return {"started": False, **_triage}
        _triage["running"] = True
    if redo:
        from harness import triage
        _with_conn(triage.retriage_all)
    threading.Thread(target=_run_triage, daemon=True).start()
    return {"started": True, **_triage}


@app.get("/api/triage/status")
def triage_status() -> dict:
    with _triage_lock:
        return dict(_triage)


@app.get("/api/emails")
def get_emails(hours: int = 72, include_skipped: bool = False) -> dict:
    from harness import triage
    return _with_conn(lambda c: triage.list_emails(c, min(max(hours, 1), 168), include_skipped=include_skipped))


# --- Her feedback, standing rules, tasks from emails ---
from pydantic import BaseModel


class LabelIn(BaseModel):
    label: str | None


class RuleIn(BaseModel):
    text: str


@app.post("/api/emails/{email_id}/label")
def label_email(email_id: int, body: LabelIn) -> dict:
    from harness import triage
    if body.label not in ("yes", "no", None):
        raise HTTPException(422, "label must be yes, no or null")
    if not _with_conn(lambda c: triage.set_label(c, email_id, body.label)):
        raise HTTPException(404, "No such email")
    return {"ok": True}


@app.post("/api/emails/{email_id}/task")
def email_to_task(email_id: int) -> dict:
    from harness import triage
    r = _with_conn(lambda c: triage.add_to_today(c, email_id))
    if r is None:
        raise HTTPException(404, "No such email")
    return r


@app.get("/api/triage/rules")
def get_rules() -> dict:
    return {"items": _with_conn(lambda c: [dict(r) for r in c.execute("SELECT id, text FROM triage_rules WHERE active=1 ORDER BY id")])}


@app.post("/api/triage/rules")
def add_rule(body: RuleIn) -> dict:
    text = body.text.strip()
    if not 5 <= len(text) <= 300:
        raise HTTPException(422, "A rule should be a sentence (5 to 300 characters)")
    def go(c):
        with c:
            return c.execute("INSERT INTO triage_rules (text) VALUES (?)", (text,)).lastrowid
    return {"id": _with_conn(go)}


@app.delete("/api/triage/rules/{rule_id}")
def delete_rule(rule_id: int) -> dict:
    def go(c):
        with c:
            return c.execute("UPDATE triage_rules SET active=0 WHERE id=?", (rule_id,)).rowcount
    return {"changed": bool(_with_conn(go))}


# --- Model scoreboard ---
_score = {"running": False}
_score_lock = threading.Lock()


class ScoreIn(BaseModel):
    models: list[str]


def _run_scoreboard(models: list[str]) -> None:
    from harness import scoreboard
    conn = db.connect()
    try:
        scoreboard.run_and_store(conn, models)
    finally:
        conn.close()
        with _score_lock:
            _score["running"] = False


@app.post("/api/scoreboard/run")
def scoreboard_run(body: ScoreIn) -> dict:
    if not 1 <= len(body.models) <= 6:
        raise HTTPException(422, "Choose between 1 and 6 models")
    with _score_lock:
        if _score["running"]:
            return {"started": False}
        _score["running"] = True
    threading.Thread(target=_run_scoreboard, args=(body.models,), daemon=True).start()
    return {"started": True}


@app.get("/api/scoreboard")
def scoreboard_get() -> dict:
    from harness import scoreboard
    with _score_lock:
        running = _score["running"]
    def go(c):
        return {"latest": scoreboard.latest(c), "n_labelled": len(scoreboard.labelled(c)),
                "n_yes": c.execute("SELECT COUNT(*) FROM emails WHERE user_label='yes'").fetchone()[0]}
    return {"running": running, **_with_conn(go)}
