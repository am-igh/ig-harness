"""IG Harness API. Phase 1 skeleton: health check only."""
from contextlib import asynccontextmanager

from fastapi import FastAPI

from harness import db
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
