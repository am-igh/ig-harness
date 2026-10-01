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
