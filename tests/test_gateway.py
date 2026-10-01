"""Red-team tests for the model gateway (Phase 2 'done when': samples cannot leave the Mac).

All data here is invented. `Recorder` stands in for an external provider and remembers
everything it is sent; a test fails if it is sent something it should never see."""
import pytest

from harness import config, db
from harness.gateway import Gateway, Tier, approvals, classify
from harness.gateway.providers import Completion, ProviderUnavailable
from harness.gateway.redact import redact


class Recorder:
    external = True

    def __init__(self, name="anthropic"):
        self.name, self.calls, self.cost = name, [], 0.0

    def complete(self, prompt, system=None, max_tokens=0, json_mode=False):
        self.calls.append((prompt, system))
        return Completion(f"echo: {prompt}", self.cost)


class FakeLocal:
    external, name, model = False, "local", "fake-local"

    def __init__(self, fail=False):
        self.calls, self.fail = [], fail

    def complete(self, prompt, system=None, max_tokens=0, json_mode=False):
        if self.fail:
            raise ProviderUnavailable("down")
        self.calls.append(prompt)
        return Completion("local answer")


@pytest.fixture
def env(tmp_path):
    path = tmp_path / "t.db"
    c = db.connect(path); db.migrate(c); c.close()
    ext, loc = Recorder(), FakeLocal()
    gw = Gateway(connect=lambda: db.connect(path), providers={"local": loc, "anthropic": ext})
    return gw, ext, loc, path


def log_rows(path):
    c = db.connect(path)
    rows = [dict(r) for r in c.execute("SELECT * FROM privacy_log ORDER BY id")]
    c.close()
    return rows


# --- Red-team samples: each must be refused for an external provider ---------------------------
S3_SAMPLES = {
    "iban": "Please wire the balance to CH93 0076 2011 6238 5295 7 by Friday.",
    "avs": "My AVS number is 756.1234.5678.97, please update the file.",
    "payroll": "Salary for September: gross 8,500, see the payslip attached.",
    "health": "She will be off for two weeks; the medical certificate is attached.",
    "credential": "Login for the portal, password: hunter2-correct-horse",
    "api key": "Use key sk-ant-api03-AAAAAAAAAAAAAAAAAAAAAAAAAAAA for the call.",
}
S2_SAMPLES = {
    "invoice amount": "Invoice 4521 from the printer, CHF 12'500.00, due 30 days.",
    "bank wording": "Relevé de compte UBS, Q3: two unmatched debits.",
    "euro amount": "The funder will transfer EUR 40,000 in two instalments.",
}


@pytest.mark.parametrize("name,text", {**S3_SAMPLES, **S2_SAMPLES}.items())
def test_sensitive_samples_never_reach_external_even_from_an_internal_source(env, name, text):
    gw, ext, loc, path = env
    r = gw.complete(text, source="task", purpose="redteam", prefer="anthropic")   # 'task' is S1 by source
    assert r.outcome == "blocked" and not r.ok
    assert ext.calls == [], f"{name}: sample reached the external provider"
    assert r.tier >= Tier.S2


@pytest.mark.parametrize("source", ["email", "gmail", "bank_statement", "invoice", "contract", "funder", "calendar"])
def test_s2_sources_never_go_external(env, source):
    gw, ext, *_ = env
    r = gw.complete("A perfectly harmless sentence.", source=source, purpose="t", prefer="anthropic")
    assert r.outcome == "blocked" and ext.calls == [] and r.tier == Tier.S2


@pytest.mark.parametrize("source", ["payroll", "hr", "personal", "credentials"])
def test_s3_sources_never_go_external(env, source):
    gw, ext, *_ = env
    r = gw.complete("Harmless text.", source=source, purpose="t", prefer="anthropic")
    assert r.outcome == "blocked" and ext.calls == [] and r.tier == Tier.S3


def test_unknown_source_is_treated_as_confidential(env):
    gw, ext, *_ = env
    r = gw.complete("Hello.", source="something-new", purpose="t", prefer="anthropic")
    assert r.tier == Tier.S2 and r.outcome == "blocked" and ext.calls == []


def test_personal_space_is_always_s3_even_with_override(env):
    gw, ext, *_ = env
    r = gw.complete("Public newsletter text.", source="newsletter", purpose="t", prefer="anthropic",
                    space="personal", override_tier=Tier.S0)
    assert r.tier == Tier.S3 and r.outcome == "blocked" and ext.calls == []


def test_secrets_hidden_in_the_system_prompt_are_caught_too(env):
    gw, ext, *_ = env
    r = gw.complete("Summarise.", source="task", purpose="t", prefer="anthropic",
                    system="password: swordfish and IBAN CH93 0076 2011 6238 5295 7")
    assert r.outcome == "blocked" and ext.calls == []


def test_unknown_provider_name_is_refused(env):
    gw, *_ = env
    assert gw.complete("x", source="newsletter", purpose="t", prefer="mystery").outcome == "blocked"


def test_disabled_external_provider_cannot_be_called_in_phase_2(tmp_path):
    path = tmp_path / "d.db"
    c = db.connect(path); db.migrate(c); c.close()
    gw = Gateway(connect=lambda: db.connect(path))          # real default providers
    r = gw.complete("Public text.", source="newsletter", purpose="t", prefer="anthropic")
    assert r.outcome == "error" and "not enabled" in r.reason


# --- Local model: everything may go, nothing leaves the Mac ------------------------------------
def test_s3_is_answered_locally_and_logged_as_local(env):
    gw, ext, loc, path = env
    r = gw.complete(S3_SAMPLES["iban"], source="gmail", purpose="triage", prefer="local")
    assert r.ok and r.text == "local answer" and r.tier == Tier.S3
    assert ext.calls == [] and len(loc.calls) == 1
    row = log_rows(path)[-1]
    assert row["provider"] == "local" and row["tier"] == "S3" and row["cost_chf"] == 0 and row["outcome"] == "ok"


def test_local_model_down_is_an_error_not_a_fallback_to_external(env):
    gw, ext, loc, path = env
    loc.fail = True
    r = gw.complete("anything", source="gmail", purpose="triage", prefer="local")
    assert r.outcome == "error" and ext.calls == []


# --- Permitted external calls: redacted, logged, capped ----------------------------------------
def test_s1_external_is_redacted_and_restored_locally(env):
    gw, ext, loc, path = env
    text = "Remind daniel@ict4peace.org and Daniel Stauffacher about https://example.org/doc?id=7 and call +41 22 555 12 34."
    r = gw.complete(text, source="task", purpose="t", prefer="anthropic", known_names=("Daniel Stauffacher",))
    assert r.ok
    sent = ext.calls[0][0]
    for leaked in ("daniel@ict4peace.org", "Stauffacher", "example.org", "555 12 34"):
        assert leaked not in sent
    assert "[EMAIL_1]" in sent and "[PERSON_1]" in sent
    assert "daniel@ict4peace.org" in r.text and "Daniel Stauffacher" in r.text     # restored on the Mac
    row = log_rows(path)[-1]
    assert row["redacted"] == 1 and row["provider"] == "anthropic"


def test_privacy_log_has_sizes_but_never_content(env):
    gw, ext, loc, path = env
    gw.complete("Secret plan for Daniel Stauffacher", source="task", purpose="plan", prefer="anthropic", known_names=("Daniel Stauffacher",))
    gw.complete(S3_SAMPLES["iban"], source="task", purpose="plan", prefer="anthropic")
    rows = log_rows(path)
    assert len(rows) == 2 and rows[0]["in_chars"] > 0
    assert "Stauffacher" not in str(rows) and "CH93" not in str(rows)


def test_blocked_attempts_are_logged_too(env):
    gw, ext, loc, path = env
    gw.complete(S3_SAMPLES["avs"], source="task", purpose="t", prefer="anthropic")
    row = log_rows(path)[-1]
    assert row["outcome"] == "blocked" and row["tier"] == "S3"


def _spend(path, chf):
    c = db.connect(path)
    from harness.config import now_local
    c.execute("INSERT INTO privacy_log (ts,request_id,provider,tier,purpose,outcome,cost_chf) VALUES (?,?,?,?,?,?,?)",
              (now_local().strftime("%Y-%m-%d %H:%M:%S"), "x", "anthropic", "S1", "t", "ok", chf))
    c.commit(); c.close()


def test_budget_warns_at_30_and_blocks_at_40_but_not_local(env):
    gw, ext, loc, path = env
    _spend(path, 30.0)
    r = gw.complete("Public.", source="newsletter", purpose="t", prefer="anthropic")
    assert r.ok and r.budget_warning is True
    _spend(path, 10.0)
    r = gw.complete("Public.", source="newsletter", purpose="t", prefer="anthropic")
    assert r.outcome == "blocked" and "cap" in r.reason
    assert len(ext.calls) == 1
    assert gw.complete("Public.", source="newsletter", purpose="t", prefer="local").ok   # local unaffected


# --- S2 approval flow (switch is OFF in production) --------------------------------------------
def test_s2_external_is_refused_while_switch_is_off_even_if_approved(env):
    gw, ext, loc, path = env
    assert config.EXTERNAL_S2_ENABLED is False
    c = db.connect(path)
    aid = approvals.request_approval(c, Tier.S2, "anthropic", "t", "Harmless text.")
    approvals.decide(c, aid, True); c.close()
    r = gw.complete("Harmless text.", source="email", purpose="t", prefer="anthropic", approval_id=aid)
    assert r.outcome == "blocked" and ext.calls == []


def test_s2_external_needs_approval_of_exactly_this_redacted_text(env, monkeypatch):
    monkeypatch.setattr(config, "EXTERNAL_S2_ENABLED", True)
    gw, ext, loc, path = env
    r = gw.complete("Note for a@b.org.", source="email", purpose="t", prefer="anthropic")
    assert r.outcome == "needs_approval" and ext.calls == [] and r.approval_id
    c = db.connect(path)
    assert c.execute("SELECT preview FROM approvals").fetchone()[0] == "Note for [EMAIL_1]."   # she sees placeholders only
    approvals.decide(c, r.approval_id, True); c.close()
    ok = gw.complete("Note for a@b.org.", source="email", purpose="t", prefer="anthropic", approval_id=r.approval_id)
    assert ok.ok and ext.calls[0][0] == "Note for [EMAIL_1]."
    other = gw.complete("A different note.", source="email", purpose="t", prefer="anthropic", approval_id=r.approval_id)
    assert other.outcome == "needs_approval" and len(ext.calls) == 1        # approval doesn't transfer


def test_s2_rejected_approval_never_sends(env, monkeypatch):
    monkeypatch.setattr(config, "EXTERNAL_S2_ENABLED", True)
    gw, ext, loc, path = env
    r = gw.complete("Memo.", source="email", purpose="t", prefer="anthropic")
    c = db.connect(path); approvals.decide(c, r.approval_id, False); c.close()
    assert gw.complete("Memo.", source="email", purpose="t", prefer="anthropic", approval_id=r.approval_id).outcome == "needs_approval"
    assert ext.calls == []


def test_s3_is_refused_even_with_the_s2_switch_on(env, monkeypatch):
    monkeypatch.setattr(config, "EXTERNAL_S2_ENABLED", True)
    gw, ext, *_ = env
    r = gw.complete(S3_SAMPLES["iban"], source="email", purpose="t", prefer="anthropic")
    assert r.outcome == "blocked" and ext.calls == []


# --- Classification and redaction details ------------------------------------------------------
def test_classification_reasons_are_reported():
    c = classify("Invoice 7, CHF 100", source="task")
    assert c.tier == Tier.S2 and "detected:amount" in c.reasons


def test_override_can_lower_work_items_and_is_recorded():
    c = classify("Harmless.", source="email", override=Tier.S1)
    assert c.tier == Tier.S1 and "override:S1" in c.reasons


def test_redaction_roundtrip_and_stable_placeholders():
    r = redact("Write to a@b.org and a@b.org again, IBAN CH93 0076 2011 6238 5295 7, AVS 756.1234.5678.97, CHF 1'200.50.")
    assert r.text.count("[EMAIL_1]") == 2 and "[IBAN_1]" in r.text and "[AVS_1]" in r.text and "[AMOUNT_1]" in r.text
    assert "CH93" not in r.text and "756." not in r.text and "1'200" not in r.text
    assert r.restore(r.text).startswith("Write to a@b.org and a@b.org again")
