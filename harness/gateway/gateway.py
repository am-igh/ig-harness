"""The router. classify -> policy -> (redact) -> budget -> provider -> privacy log."""
import sqlite3
import uuid
from dataclasses import dataclass, field
from typing import Callable

from harness import config, db
from harness.gateway import approvals, budget
from harness.gateway.privacy_log import log_call
from harness.gateway.providers import ProviderUnavailable, default_providers
from harness.gateway.redact import redact
from harness.gateway.tiers import Tier, classify

# Which providers each tier may reach (rule 3). S2 external is additionally gated (see _check_external).
ALLOWED: dict[Tier, set[str]] = {
    Tier.S0: {"local", "infomaniak", "anthropic", "openrouter"},
    Tier.S1: {"local", "infomaniak", "anthropic"},
    Tier.S2: {"local"},
    Tier.S3: {"local"},
}


# Providers S2 may use ONLY when config.EXTERNAL_S2_ENABLED is on, after redaction and approval.
S2_EXTERNAL_WHEN_ENABLED = {"infomaniak", "anthropic"}


def _allowed(tier: Tier) -> set[str]:
    if tier == Tier.S2 and config.EXTERNAL_S2_ENABLED:
        return ALLOWED[tier] | S2_EXTERNAL_WHEN_ENABLED
    return ALLOWED[tier]                                  # S3: local only, always


@dataclass
class GatewayResult:
    ok: bool
    outcome: str                      # ok | blocked | needs_approval | error
    text: str = ""
    tier: Tier = Tier.S2
    provider: str = ""
    reason: str = ""
    request_id: str = ""
    approval_id: int | None = None
    budget_warning: bool = False
    reasons: list[str] = field(default_factory=list)


class Gateway:
    def __init__(self, connect: Callable[[], sqlite3.Connection] = db.connect, providers: dict | None = None):
        self._connect = connect
        self.providers = providers or default_providers()

    def complete(self, prompt: str, *, source: str, purpose: str, system: str | None = None,
                 prefer: str = "local", space: str = "work", override_tier: Tier | None = None,
                 known_names: tuple[str, ...] = (), approval_id: int | None = None,
                 max_tokens: int = 1024, json_mode: bool = False) -> GatewayResult:
        rid = uuid.uuid4().hex[:12]
        conn = self._connect()
        try:
            c = classify(prompt + "\n" + (system or ""), source, space, override_tier)
            res = GatewayResult(ok=False, outcome="blocked", tier=c.tier, provider=prefer, request_id=rid, reasons=c.reasons)
            provider = self.providers.get(prefer)

            def finish(outcome: str, detail: str = "", *, out_chars: int = 0, cost: float = 0.0,
                       redacted: bool = False, shown_provider: str | None = None) -> GatewayResult:
                res.outcome, res.reason, res.ok = outcome, detail, outcome == "ok"
                log_call(conn, request_id=rid, provider=shown_provider or prefer,
                         model=getattr(provider, "model", None), tier=c.tier, redacted=redacted,
                         in_chars=len(prompt), out_chars=out_chars, cost_chf=cost, purpose=purpose,
                         outcome=outcome, detail=detail)
                return res

            if provider is None:
                return finish("blocked", f"unknown provider {prefer}")

            if not provider.external:                       # local model: data stays on the Mac
                try:
                    out = provider.complete(prompt, system, max_tokens, json_mode)
                except ProviderUnavailable as e:
                    return finish("error", str(e))
                res.text = out.text
                return finish("ok", out_chars=len(out.text))

            # ---- external provider: every gate must pass, otherwise nothing is sent ----
            if prefer not in _allowed(c.tier):
                return finish("blocked", f"tier {c.tier} may not go to {prefer}")
            red = redact(prompt, known_names)
            red_system = redact(system, known_names).text if system else None
            if c.tier == Tier.S2:
                if not config.EXTERNAL_S2_ENABLED:
                    return finish("blocked", "S2 external is switched off", redacted=True)
                if not approvals.is_approved(conn, approval_id, prefer, red.text):
                    res.approval_id = approvals.request_approval(conn, c.tier, prefer, purpose, red.text)
                    return finish("needs_approval", "waiting for her one-click approval", redacted=True)
            state = budget.state(conn)
            if state == "blocked":
                return finish("blocked", f"monthly cap CHF {config.BUDGET_CAP_CHF:.0f} reached", redacted=True)
            res.budget_warning = state == "warn"
            try:
                out = provider.complete(red.text, red_system, max_tokens, json_mode)
            except ProviderUnavailable as e:
                return finish("error", str(e), redacted=True)
            res.text = red.restore(out.text)                # placeholders back to real values, locally
            return finish("ok", out_chars=len(out.text), cost=out.cost_chf, redacted=True)
        finally:
            conn.close()
