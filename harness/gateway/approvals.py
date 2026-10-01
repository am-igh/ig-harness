"""One-click approvals for S2 data going external (rule 3). Only reachable once
config.EXTERNAL_S2_ENABLED is switched on, which it is not. She approves the REDACTED text."""
import hashlib
import sqlite3

from harness.config import now_local


def content_hash(redacted_prompt: str) -> str:
    return hashlib.sha256(redacted_prompt.encode()).hexdigest()


def request_approval(conn: sqlite3.Connection, tier, provider: str, purpose: str, redacted_prompt: str) -> int:
    with conn:
        cur = conn.execute(
            "INSERT INTO approvals (created_at, tier, provider, purpose, content_hash, preview) VALUES (?,?,?,?,?,?)",
            (now_local().strftime("%Y-%m-%d %H:%M:%S"), str(tier), provider, purpose,
             content_hash(redacted_prompt), redacted_prompt),
        )
    return cur.lastrowid


def decide(conn: sqlite3.Connection, approval_id: int, approve: bool) -> None:
    with conn:
        conn.execute("UPDATE approvals SET status=?, decided_at=? WHERE id=? AND status='pending'",
                     ("approved" if approve else "rejected", now_local().strftime("%Y-%m-%d %H:%M:%S"), approval_id))


def is_approved(conn: sqlite3.Connection, approval_id: int | None, provider: str, redacted_prompt: str) -> bool:
    """Approved for exactly this provider and exactly this redacted text."""
    if approval_id is None:
        return False
    row = conn.execute("SELECT status, provider, content_hash FROM approvals WHERE id=?", (approval_id,)).fetchone()
    return bool(row and row["status"] == "approved" and row["provider"] == provider
                and row["content_hash"] == content_hash(redacted_prompt))
