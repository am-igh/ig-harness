"""IG Harness API. Phase 1 skeleton: health check only."""
from fastapi import FastAPI

from harness.config import DATA_DIR, VERSION

app = FastAPI(title="IG Harness", version=VERSION)


@app.get("/api/health")
def health() -> dict:
    return {
        "status": "ok",
        "version": VERSION,
        "data_dir_mounted": DATA_DIR.is_dir(),
    }
