"""Privacy log (rule 5): one row per model call, local or external. Stores sizes, never content."""
import sqlite3

from harness.config import now_local


def log_call(conn: sqlite3.Connection, *, request_id: str, provider: str, model: str | None, tier,
             redacted: bool, in_chars: int, out_chars: int, cost_chf: float, purpose: str,
             outcome: str, detail: str = "") -> None:
    with conn:
        conn.execute(
            "INSERT INTO privacy_log (ts, request_id, provider, model, tier, redacted, in_chars, out_chars, "
            "cost_chf, purpose, outcome, detail) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (now_local().strftime("%Y-%m-%d %H:%M:%S"), request_id, provider, model, str(tier),
             int(redacted), in_chars, out_chars, cost_chf, purpose, outcome, detail[:200]),
        )
