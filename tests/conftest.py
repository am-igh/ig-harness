"""Tests never touch real data: point the data directory at a throwaway folder
before the harness modules are imported (rule 8)."""
import os
import tempfile

os.environ["IG_SCAN_WATCH"] = "0"          # no background scan watcher or event reader in tests
os.environ["IG_DATA_DIR"] = tempfile.mkdtemp(prefix="ig-harness-test-")
