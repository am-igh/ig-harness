"""Settings read from environment variables. No secrets here (Keychain only)."""
import os
from pathlib import Path

DATA_DIR = Path(os.environ.get("IG_DATA_DIR", "/data"))
VERSION = "0.1.0"
