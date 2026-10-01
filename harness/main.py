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
def triage_run() -> dict:
    with _triage_lock:
        if _triage["running"]:
            return {"started": False, **_triage}
        _triage["running"] = True
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
