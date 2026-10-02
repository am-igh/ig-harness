"""Which model each job uses. Set from the model picker; the gateway still decides what data may go where.

A job has a sensitivity tier (what its data is). The picker can only choose a provider the gateway would
allow for that tier, so no choice made here can send confidential data out (rule 3)."""
import sqlite3

from harness import config
from harness.gateway.tiers import Tier

JOBS = {
    "email_triage": {"label": "Email triage", "tier": Tier.S2},   # email is confidential: local models only
    "email_draft": {"label": "Draft replies", "tier": Tier.S2},   # drafts quote her correspondence: local models only
    "doc_read": {"label": "Read scanned invoices and receipts", "tier": Tier.S2},   # invoices and receipts are confidential: local models only
}
PROVIDERS = {"local", "infomaniak", "anthropic", "openrouter"}


class SelectionRefused(ValueError):
    pass


def get_selection(conn: sqlite3.Connection, job: str) -> tuple[str, str]:
    row = conn.execute("SELECT provider, model FROM model_settings WHERE job = ?", (job,)).fetchone()
    if row and row["provider"] == "local" and row["model"]:
        return "local", row["model"]
    return "local", config.LOCAL_MODEL


def set_selection(conn: sqlite3.Connection, job: str, provider: str, model: str | None, external_ready: set[str] = frozenset()) -> None:
    from harness.gateway.gateway import _allowed       # same rule the gateway applies on every call
    if job not in JOBS:
        raise SelectionRefused(f"unknown job {job}")
    if provider not in PROVIDERS:
        raise SelectionRefused(f"unknown provider {provider}")
    if provider not in _allowed(JOBS[job]["tier"]):
        raise SelectionRefused(f"{JOBS[job]['label']} handles {JOBS[job]['tier']} data, which may only use local models")
    if provider != "local" and provider not in external_ready:
        raise SelectionRefused(f"{provider} is not set up yet (Phase 6)")
    if not model:
        raise SelectionRefused("choose a model")
    with conn:
        conn.execute("INSERT INTO model_settings (job, provider, model) VALUES (?,?,?) "
                     "ON CONFLICT (job) DO UPDATE SET provider=excluded.provider, model=excluded.model, updated_at=datetime('now')",
                     (job, provider, model))
