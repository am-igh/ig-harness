"""IG Harness API. Phase 1 skeleton: health check only."""
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
