"""External AI spend cap (rule 6): warn at CHF 30, block at CHF 40 per calendar month.
Local models are free and unaffected."""
import sqlite3
from datetime import datetime

from harness.config import BUDGET_CAP_CHF, BUDGET_WARN_CHF, now_local


def month_spend(conn: sqlite3.Connection, now: datetime | None = None) -> float:
    month = (now or now_local()).strftime("%Y-%m")
    row = conn.execute(
        "SELECT COALESCE(SUM(cost_chf), 0) FROM privacy_log WHERE provider != 'local' AND substr(ts,1,7) = ?",
        (month,),
    ).fetchone()
    return float(row[0])


def state(conn: sqlite3.Connection, now: datetime | None = None) -> str:
    """'ok' | 'warn' | 'blocked'"""
    spent = month_spend(conn, now)
    if spent >= BUDGET_CAP_CHF:
        return "blocked"
    return "warn" if spent >= BUDGET_WARN_CHF else "ok"
