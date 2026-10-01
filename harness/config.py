"""Settings read from environment variables. No secrets here (Keychain only)."""
import os
from pathlib import Path

DATA_DIR = Path(os.environ.get("IG_DATA_DIR", "/data"))
VERSION = "0.1.0"

from datetime import datetime
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Zurich")


def now_local() -> datetime:
    """Current time in Geneva. All 'today' logic uses this, not the container's UTC clock."""
    return datetime.now(TZ)

# --- Model gateway settings (CLAUDE.md rules 2-6) ---
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://ollama.internal:11434")
LOCAL_MODEL = os.environ.get("IG_LOCAL_MODEL", "qwen3:8b")   # her favourite 27B once pulled
BUDGET_WARN_CHF = 30.0
BUDGET_CAP_CHF = 40.0
# S2 (confidential) may only go external after redaction AND one-click approval AND once
# data-processing agreements are confirmed. This switch stays OFF until she says otherwise.
# Deliberately a constant, not an environment variable.
EXTERNAL_S2_ENABLED = False
