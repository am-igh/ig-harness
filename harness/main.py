"""IG Harness API. Phase 1 skeleton: health check only."""
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException

from harness import db, deadlines, today as today_view
from harness.config import DATA_DIR, VERSION
from harness.importers.run import run_all


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create or upgrade the database when the API starts.
    conn = db.connect()
    db.migrate(conn)
    conn.close()
    yield


app = FastAPI(title="IG Harness", version=VERSION, lifespan=lifespan)


@app.get("/api/health")
def health() -> dict:
    conn = db.connect()
    schema = db.schema_version(conn)
    conn.close()
    return {
        "schema_version": schema,
        "status": "ok",
        "version": VERSION,
        "data_dir_mounted": DATA_DIR.is_dir(),
    }


@app.post("/api/import")
def import_now() -> dict:
    """Re-read Suivi.xlsx and Registre_Projets.xlsx (read-only) and report what changed."""
    return {"reports": run_all()}


def _with_conn(fn):
    conn = db.connect()
    try:
        return fn(conn)
    finally:
        conn.close()


@app.get("/api/today")
def get_today() -> dict:
    return _with_conn(today_view.build_today)


@app.get("/api/done")
def get_done(days: int = 7, q: str = "") -> dict:
    """The Done record: days=0 means all time."""
    from harness.config import now_local
    items = _with_conn(lambda c: today_view.done_list(c, now_local().date(), days or None, q))
    return {"items": items}


@app.get("/api/done/week")
def get_done_week() -> dict:
    return get_done(7, "")


@app.get("/api/deadlines/{deadline_id}")
def get_deadline(deadline_id: int) -> dict:
    from harness.config import now_local
    d = _with_conn(lambda c: today_view.deadline_detail(c, deadline_id, now_local().date()))
    if d is None:
        raise HTTPException(404, "No such deadline")
    return d


@app.post("/api/items/{item_type}/{item_id}/done")
def tick(item_type: str, item_id: int) -> dict:
    if item_type not in deadlines.ITEM_TYPES:
        raise HTTPException(404, "Unknown item type")
    return {"changed": _with_conn(lambda c: deadlines.mark_done(c, item_type, item_id))}


@app.post("/api/items/{item_type}/{item_id}/undo")
def untick(item_type: str, item_id: int) -> dict:
    if item_type not in deadlines.ITEM_TYPES:
        raise HTTPException(404, "Unknown item type")
    return {"changed": _with_conn(lambda c: deadlines.mark_undone(c, item_type, item_id))}


@app.get("/api/gateway/status")
def gateway_status() -> dict:
    """Is the local model reachable, and where does the external-spend budget stand."""
    from harness.gateway import budget
    from harness.gateway.providers import OllamaProvider
    local = OllamaProvider().status()
    conn = db.connect()
    try:
        spend, state = budget.month_spend(conn), budget.state(conn)
    finally:
        conn.close()
    return {"local": local, "external_spend_chf": round(spend, 2), "budget_state": state}


@app.get("/api/privacy-log")
def privacy_log(limit: int = 50) -> dict:
    rows = _with_conn(lambda c: [dict(r) for r in c.execute(
        "SELECT ts, provider, model, tier, redacted, in_chars, out_chars, cost_chf, purpose, outcome, detail "
        "FROM privacy_log ORDER BY id DESC LIMIT ?", (min(limit, 500),))])
    return {"items": rows}


# --- Email triage (runs on demand; the local model can take a while, so it runs in the background) ---
_triage = {"running": False, "last": None, "finished_at": None}
_triage_lock = threading.Lock()


def _run_triage() -> None:
    from harness import triage
    from harness.config import now_local
    conn = db.connect()
    try:
        result = triage.triage_pending(conn)
    except Exception as e:  # never crash the API thread
        result = {"error": f"{type(e).__name__}: {e}"}
    finally:
        conn.close()
        with _triage_lock:
            _triage.update(running=False, last=result, finished_at=now_local().isoformat(timespec="seconds"))


@app.post("/api/triage/run")
def triage_run(redo: bool = False) -> dict:
    with _triage_lock:
        if _triage["running"]:
            return {"started": False, **_triage}
        _triage["running"] = True
    if redo:
        from harness import triage
        _with_conn(triage.retriage_all)
    threading.Thread(target=_run_triage, daemon=True).start()
    return {"started": True, **_triage}


@app.get("/api/triage/status")
def triage_status() -> dict:
    with _triage_lock:
        return dict(_triage)


@app.get("/api/emails")
def get_emails(hours: int = 72, include_skipped: bool = False) -> dict:
    from harness import triage
    return _with_conn(lambda c: triage.list_emails(c, min(max(hours, 1), 168), include_skipped=include_skipped))


# --- Her feedback, standing rules, tasks from emails ---
from pydantic import BaseModel


class LabelIn(BaseModel):
    label: str | None


class RuleIn(BaseModel):
    text: str


@app.post("/api/emails/{email_id}/label")
def label_email(email_id: int, body: LabelIn) -> dict:
    from harness import triage
    if body.label not in ("yes", "no", None):
        raise HTTPException(422, "label must be yes, no or null")
    if not _with_conn(lambda c: triage.set_label(c, email_id, body.label)):
        raise HTTPException(404, "No such email")
    return {"ok": True}


@app.post("/api/emails/{email_id}/task")
def email_to_task(email_id: int) -> dict:
    from harness import triage
    r = _with_conn(lambda c: triage.add_to_today(c, email_id))
    if r is None:
        raise HTTPException(404, "No such email")
    return r


@app.get("/api/triage/rules")
def get_rules() -> dict:
    return {"items": _with_conn(lambda c: [dict(r) for r in c.execute("SELECT id, text FROM triage_rules WHERE active=1 ORDER BY id")])}


@app.post("/api/triage/rules")
def add_rule(body: RuleIn) -> dict:
    text = body.text.strip()
    if not 5 <= len(text) <= 300:
        raise HTTPException(422, "A rule should be a sentence (5 to 300 characters)")
    def go(c):
        with c:
            return c.execute("INSERT INTO triage_rules (text) VALUES (?)", (text,)).lastrowid
    return {"id": _with_conn(go)}


@app.delete("/api/triage/rules/{rule_id}")
def delete_rule(rule_id: int) -> dict:
    def go(c):
        with c:
            return c.execute("UPDATE triage_rules SET active=0 WHERE id=?", (rule_id,)).rowcount
    return {"changed": bool(_with_conn(go))}


# --- Model scoreboard ---
_score = {"running": False}
_score_lock = threading.Lock()


class ScoreIn(BaseModel):
    models: list[str]


def _run_scoreboard(models: list[str]) -> None:
    from harness import scoreboard
    conn = db.connect()
    try:
        scoreboard.run_and_store(conn, models)
    finally:
        conn.close()
        with _score_lock:
            _score["running"] = False


@app.post("/api/scoreboard/run")
def scoreboard_run(body: ScoreIn) -> dict:
    if not 1 <= len(body.models) <= 6:
        raise HTTPException(422, "Choose between 1 and 6 models")
    with _score_lock:
        if _score["running"]:
            return {"started": False}
        _score["running"] = True
    threading.Thread(target=_run_scoreboard, args=(body.models,), daemon=True).start()
    return {"started": True}


@app.get("/api/scoreboard")
def scoreboard_get() -> dict:
    from harness import scoreboard
    with _score_lock:
        running = _score["running"]
    def go(c):
        return {"latest": scoreboard.latest(c), "n_labelled": len(scoreboard.labelled(c)),
                "n_yes": c.execute("SELECT COUNT(*) FROM emails WHERE user_label='yes'").fetchone()[0]}
    return {"running": running, **_with_conn(go)}


@app.post("/api/emails/{email_id}/done")
def email_done(email_id: int) -> dict:
    return {"changed": _with_conn(lambda c: deadlines.mark_done(c, "email", email_id))}


@app.post("/api/emails/{email_id}/undo")
def email_undo(email_id: int) -> dict:
    return {"changed": _with_conn(lambda c: deadlines.mark_undone(c, "email", email_id))}


# --- Model picker ---
EXTERNAL = [
    {"provider": "infomaniak", "label": "Infomaniak AI Tools", "hosting": "Swiss-hosted", "tiers": "S0–S1 (S2 only after redaction and your approval, which is switched off)"},
    {"provider": "anthropic", "label": "Claude API", "hosting": "Anthropic, US", "tiers": "S0–S1 (S2 only after redaction and your approval, which is switched off)"},
    {"provider": "openrouter", "label": "OpenRouter", "hosting": "for experiments", "tiers": "S0 (public data) only"},
]


class SelectIn(BaseModel):
    job: str
    provider: str
    model: str


@app.get("/api/models")
def get_models() -> dict:
    from harness.gateway import budget
    from harness.gateway.providers import OllamaProvider
    from harness.gateway.settings import JOBS, get_selection
    local = OllamaProvider().status()
    def go(c):
        jobs = []
        for job, meta in JOBS.items():
            provider, model = get_selection(c, job)
            jobs.append({"job": job, "label": meta["label"], "tier": str(meta["tier"]), "local_only": True,
                         "provider": provider, "model": model, "model_installed": model in local["installed"]})
        return {"jobs": jobs, "spend": round(budget.month_spend(c), 2), "budget_state": budget.state(c)}
    return {"local": {"up": local["up"], "models": local["models"]}, "external": [{**e, "status": "not_set_up",
            "note": "Needs an API key in your Mac's Keychain and a secure route out of the harness (Phase 6)."} for e in EXTERNAL],
            "cap_chf": 40, **_with_conn(go)}


@app.post("/api/models/select")
def select_model(body: SelectIn) -> dict:
    from harness.gateway.providers import OllamaProvider
    from harness.gateway.settings import JOBS, SelectionRefused, set_selection
    if body.job not in JOBS:
        raise HTTPException(404, "Unknown job")
    if body.provider == "local" and body.model not in OllamaProvider().status()["installed"]:
        raise HTTPException(422, f"{body.model} is not installed in Ollama")
    try:
        _with_conn(lambda c: set_selection(c, body.job, body.provider, body.model))
    except SelectionRefused as e:
        raise HTTPException(422, str(e))
    return {"ok": True, "job": body.job, "provider": body.provider, "model": body.model}


class EditIn(BaseModel):
    title: str | None = None
    due: str | None = None
    reset: bool = False


@app.patch("/api/items/{item_type}/{item_id}")
def edit_item_endpoint(item_type: str, item_id: int, body: EditIn) -> dict:
    from harness import items
    if item_type not in items.TABLES:
        raise HTTPException(404, "Unknown item type")
    try:
        found = _with_conn(lambda c: items.edit_item(c, item_type, item_id, title=body.title, due=body.due,
                                                     set_due="due" in body.model_fields_set, reset=body.reset))
    except items.EditRefused as e:
        raise HTTPException(422, str(e))
    if not found:
        raise HTTPException(404, "No such item")
    return {"ok": True}


@app.get("/api/items/{item_type}/{item_id}/reveal")
def reveal_item(item_type: str, item_id: int) -> dict:
    """Details of a masked (personal) item, shown only because she clicked it."""
    from harness import items
    if item_type not in (*items.TABLES, "email"):
        raise HTTPException(404, "Unknown item type")
    d = _with_conn(lambda c: items.reveal(c, item_type, item_id))
    if d is None:
        raise HTTPException(404, "No such item")
    return d


# --- Style profiles: how she writes to each person (learned from past correspondence, correctable) ---
class ProfileIn(BaseModel):
    language: str | None = None
    formality: str | None = None
    pronoun: str | None = None
    greeting: str | None = None
    closing: str | None = None
    notes: str | None = None


class SignatureIn(BaseModel):
    signature: str


@app.get("/api/style/profiles")
def get_profiles() -> dict:
    def go(c):
        rows = c.execute("SELECT s.*, p.name, p.org, p.role FROM style_profiles s LEFT JOIN people p ON p.email = s.person_email "
                         "ORDER BY s.n_mine DESC, s.n_theirs DESC, s.person_email")
        return [dict(r) for r in rows]
    return {"items": _with_conn(go)}


@app.patch("/api/style/profiles/{email}")
def edit_profile(email: str, body: ProfileIn) -> dict:
    sent = body.model_fields_set
    checks = {"language": {None, "en", "fr", "de", "it", "es"}, "formality": {None, "formal", "informal", "neutral"},
              "pronoun": {None, "vous", "tu", "Sie", "du"}}
    for k, allowed in checks.items():
        if k in sent and getattr(body, k) not in allowed:
            raise HTTPException(422, f"{k} must be one of {sorted(x for x in allowed if x)} or empty")
    for k, n in (("greeting", 120), ("closing", 80), ("notes", 300)):
        if k in sent and getattr(body, k) and len(getattr(body, k)) > n:
            raise HTTPException(422, f"{k} is too long (max {n})")
    def go(c):
        if c.execute("SELECT 1 FROM style_profiles WHERE person_email=?", (email.lower(),)).fetchone() is None:
            c.execute("INSERT INTO style_profiles (person_email, confidence, source) VALUES (?, 'none', 'edited')", (email.lower(),))
        with c:
            for k in sent:
                c.execute(f"UPDATE style_profiles SET {k} = ? WHERE person_email = ?", (getattr(body, k) or None, email.lower()))
            c.execute("UPDATE style_profiles SET source='edited', updated_at=datetime('now') WHERE person_email=?", (email.lower(),))
        return True
    return {"ok": _with_conn(go)}


@app.post("/api/style/profiles/{email}/relearn")
def relearn_profile(email: str) -> dict:
    from harness import style
    def go(c):
        with c:
            c.execute("UPDATE style_profiles SET source='learned' WHERE person_email=?", (email.lower(),))
        return style.rebuild_profiles(c)
    return _with_conn(go)


@app.get("/api/style/signature")
def get_signature() -> dict:
    def go(c):
        g = lambda k: c.execute("SELECT value, source FROM draft_settings WHERE key=?", (k,)).fetchone()
        eff, learned = g("signature"), g("signature_learned")
        return {"signature": eff["value"] if eff else "", "source": eff["source"] if eff else "none",
                "learned": learned["value"] if learned else None}
    return _with_conn(go)


@app.put("/api/style/signature")
def put_signature(body: SignatureIn) -> dict:
    text = body.signature.strip()
    if len(text) > 600:
        raise HTTPException(422, "The signature is too long (max 600 characters)")
    def go(c):
        with c:
            c.execute("INSERT INTO draft_settings (key, value, source) VALUES ('signature', ?, 'edited') "
                      "ON CONFLICT (key) DO UPDATE SET value=excluded.value, source='edited', updated_at=datetime('now')", (text,))
    _with_conn(go)
    return {"ok": True}
