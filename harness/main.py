"""IG Harness API. Phase 1 skeleton: health check only."""
import os
import threading
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request

from harness import db, deadlines, today as today_view
from harness.config import DATA_DIR, VERSION
from harness.importers.run import run_all


def _collector() -> None:
    """Every few seconds, pick up the Mac-side worker's answers about drafts."""
    import time
    from harness import drafting
    while True:
        try:
            c = db.connect()
            try:
                drafting.collect_results(c, DATA_DIR / "draft_outbox")
            finally:
                c.close()
        except Exception:
            pass
        time.sleep(3)


def _scan_watcher():
    """Every few seconds: notice new scans in the Scan-Inbox folder and read them (on this Mac, with the local model)."""
    from harness import scans
    while True:
        try:
            c = db.connect()
            try:
                scans.tick(c)
            finally:
                c.close()
        except Exception:
            pass
        time.sleep(8)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create or upgrade the database when the API starts.
    conn = db.connect()
    db.migrate(conn)
    conn.close()
    threading.Thread(target=_collector, daemon=True).start()
    if os.environ.get("IG_SCAN_WATCH", "1") != "0":
        threading.Thread(target=_scan_watcher, daemon=True).start()
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


@app.get("/api/triage/watch")
def get_watch() -> dict:
    return {"items": _with_conn(lambda c: [dict(r) for r in c.execute("SELECT id, name FROM watch_names WHERE active=1 ORDER BY id")])}


@app.post("/api/triage/watch")
def add_watch(body: RuleIn) -> dict:
    name = " ".join(body.text.split())
    if not 3 <= len(name) <= 80:
        raise HTTPException(422, "Give a person's name (3 to 80 characters)")
    def go(c):
        with c:
            return c.execute("INSERT INTO watch_names (name) VALUES (?)", (name,)).lastrowid
    return {"id": _with_conn(go)}


@app.delete("/api/triage/watch/{watch_id}")
def delete_watch(watch_id: int) -> dict:
    def go(c):
        with c:
            return c.execute("UPDATE watch_names SET active=0 WHERE id=?", (watch_id,)).rowcount
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


# --- Draft replies and reminders (drafts are text for her review; Gmail is only touched after she approves) ---
class DraftRequestIn(BaseModel):
    tone: str | None = None
    language: str | None = None
    instruction: str | None = None
    thread_id: str | None = None
    new_message: bool = False


class DraftApproveIn(BaseModel):
    body: str | None = None
    subject: str | None = None
    to: list[str] | None = None
    cc: list[str] | None = None


def _drafting(fn):
    from harness import drafting
    try:
        return _with_conn(fn)
    except drafting.DraftRefused as e:
        raise HTTPException(422, str(e))


@app.post("/api/emails/{email_id}/draft")
def draft_reply(email_id: int, body: DraftRequestIn) -> dict:
    from harness import drafting
    from harness.gateway import Gateway
    return _drafting(lambda c: drafting.generate_reply(c, Gateway(), email_id, tone=body.tone, language=body.language, instruction=body.instruction))


@app.get("/api/emails/{email_id}/draft")
def latest_draft(email_id: int) -> dict:
    from harness import drafting
    def go(c):
        r = c.execute("SELECT id FROM draft_requests WHERE email_id=? AND status != 'cancelled' ORDER BY created_at DESC LIMIT 1", (email_id,)).fetchone()
        return {"draft": drafting.view(c, r["id"]) if r else None}
    return _with_conn(go)


@app.get("/api/drafts/agent")
def draft_agent() -> dict:
    from harness import drafting
    return {"alive": drafting.agent_alive(DATA_DIR / "draft_outbox")}


@app.get("/api/drafts/{draft_id}")
def get_draft(draft_id: str) -> dict:
    from harness import drafting
    def go(c):
        drafting.collect_results(c, DATA_DIR / "draft_outbox")
        return drafting.view(c, draft_id)
    d = _with_conn(go)
    if d is None:
        raise HTTPException(404, "No such draft")
    return d


@app.post("/api/drafts/{draft_id}/approve")
def approve_draft(draft_id: str, body: DraftApproveIn) -> dict:
    """She clicked 'Save to Gmail' on this exact text."""
    from harness import drafting
    return _drafting(lambda c: drafting.approve(c, draft_id, DATA_DIR / "draft_outbox", body=body.body, subject=body.subject, to=body.to, cc=body.cc))


@app.post("/api/drafts/{draft_id}/cancel")
def cancel_draft(draft_id: str) -> dict:
    from harness import drafting
    return {"changed": _with_conn(lambda c: drafting.cancel(c, draft_id))}


@app.get("/api/waiting/{waiting_id}/threads")
def waiting_threads(waiting_id: int) -> dict:
    from harness import drafting
    return _drafting(lambda c: drafting.reminder_threads(c, waiting_id))


@app.post("/api/waiting/{waiting_id}/draft")
def draft_reminder(waiting_id: int, body: DraftRequestIn) -> dict:
    from harness import drafting
    from harness.gateway import Gateway
    return _drafting(lambda c: drafting.generate_reminder(c, Gateway(), waiting_id, thread_id=body.thread_id, new_message=body.new_message,
                                                          tone=body.tone, language=body.language, instruction=body.instruction))


# --- Refresh agent status (the agent runs on the Mac; it writes a status file the screen reads) ---
@app.get("/api/refresh/status")
def refresh_status() -> dict:
    from harness import refresh
    from harness.config import now_local
    return refresh.summary(refresh.read_status(DATA_DIR), now_local(), refresh.agent_alive(DATA_DIR))


@app.post("/api/refresh/now")
def refresh_now() -> dict:
    """The 'Refresh now' button: the Mac-side agent picks the request up within a few seconds."""
    from harness import refresh
    from harness.config import now_local
    refresh.request_refresh(DATA_DIR, now_local())
    return {"requested": True, "agent_alive": refresh.agent_alive(DATA_DIR)}


# --- Notes and follow-ups ---
class NoteIn(BaseModel):
    text: str
    kind: str = "note"
    parent_type: str | None = None
    parent_id: int | None = None
    due: str | None = None
    personal: bool = False


def _notes(fn):
    from harness import notes
    try:
        return _with_conn(fn)
    except notes.NoteRefused as e:
        raise HTTPException(422, str(e))


@app.post("/api/notes")
def create_note(body: NoteIn) -> dict:
    from harness import notes
    return _notes(lambda c: notes.add_note(c, body.text, kind=body.kind, parent_type=body.parent_type, parent_id=body.parent_id, due=body.due, personal=body.personal))


@app.get("/api/notes/log")
def notes_log(days: int = 30, q: str = "") -> dict:
    from harness import notes
    return {"items": _with_conn(lambda c: notes.log(c, days or None, q))}


@app.get("/api/notes")
def notes_for(parent_type: str, parent_id: int) -> dict:
    from harness import notes
    if parent_type not in notes.PARENT_TYPES:
        raise HTTPException(404, "Unknown item type")
    return {"items": _with_conn(lambda c: notes.for_parent(c, parent_type, parent_id))}


@app.get("/api/notes/{note_id}/reveal")
def reveal_note(note_id: int) -> dict:
    from harness import notes
    d = _with_conn(lambda c: notes.reveal(c, note_id))
    if d is None:
        raise HTTPException(404, "No such note")
    return d


@app.delete("/api/notes/{note_id}")
def remove_note(note_id: int) -> dict:
    from harness import notes
    return {"changed": _with_conn(lambda c: notes.delete_note(c, note_id))}


# --- Calendar widget ---
@app.get("/api/calendar")
def calendar_range(start: str, end: str) -> dict:
    from datetime import date
    from harness import calendar_view
    try:
        a, b = date.fromisoformat(start), date.fromisoformat(end)
        return _with_conn(lambda c: calendar_view.build_range(c, a, b))
    except (ValueError, calendar_view.BadRange) as e:
        raise HTTPException(422, str(e))


# --- Audit readiness: her checker (controle_justificatifs.py), run unchanged inside the harness ---
def _audit_year(year: str | None) -> str:
    from harness import audit
    years = audit.years_available(audit.ROOT)
    if not years:
        raise HTTPException(404, "The audit folder is not connected")
    y = year or years[-1]
    if y not in years:
        raise HTTPException(404, f"No audit folder for {y}")
    return y


@app.get("/api/audit/status")
def audit_status(year: str | None = None) -> dict:
    from harness import audit
    if not audit.configured(audit.ROOT):
        return {"configured": False, "years": [], "running": False, "latest": None, "last_error": None, "stale": False}
    return _with_conn(lambda c: audit.status(c, audit.ROOT, _audit_year(year)))


@app.post("/api/audit/run")
def audit_run(year: str | None = None) -> dict:
    from harness import audit
    y = _audit_year(year)
    return {"started": audit.start_background(db.connect, audit.ROOT, y), "year": y}


@app.get("/api/audit/lines")
def audit_lines(year: str | None = None, statut: str | None = None) -> dict:
    from harness import audit
    return {"items": _with_conn(lambda c: audit.lines(c, _audit_year(year), statut))}


@app.get("/api/audit/compare")
def audit_compare(year: str | None = None) -> dict:
    from harness import audit
    return _with_conn(lambda c: audit.compare_with_report(c, audit.ROOT, _audit_year(year)))


# --- Projects tab (from Suivi's Codes, commitments and journal, plus the project register) ---
@app.get("/api/projects")
def projects_overview() -> dict:
    from harness import projects
    from harness.config import now_local
    return _with_conn(lambda c: projects.build_projects(c, now_local().date()))


@app.get("/api/projects/{code}")
def project_detail(code: str) -> dict:
    from harness import projects
    from harness.config import now_local
    d = _with_conn(lambda c: projects.project_detail(c, code.upper(), now_local().date()))
    if d is None:
        raise HTTPException(404, "No such project")
    return d


# --- Bank statement filing (preview, approve; the Mac-side filer writes the new file) ---
@app.post("/api/filing/upload")
async def filing_upload(request: Request) -> dict:
    from urllib.parse import unquote
    from harness import audit, filing
    name = unquote(request.headers.get("x-filename", ""))
    content = await request.body()
    try:
        return _with_conn(lambda c: filing.stage(c, name, content))
    except (ValueError, audit.AuditError) as e:
        raise HTTPException(422, str(e))


@app.get("/api/filing")
def filing_list() -> dict:
    from harness import audit, filing
    def go(c):
        newly = filing.reconcile(c)
        return newly, filing.recent(c)
    newly, items = _with_conn(go)
    if newly and audit.configured(audit.ROOT):                       # new statements: re-run her checker so the tile includes them
        years = audit.years_available(audit.ROOT)
        audit.start_background(db.connect, audit.ROOT, years[-1])
    return {"items": items}


@app.post("/api/filing/{fid}/approve")
def filing_approve(fid: int) -> dict:
    from harness import filing
    try:
        return _with_conn(lambda c: filing.approve(c, fid))
    except KeyError:
        raise HTTPException(404, "No such filing")
    except ValueError as e:
        raise HTTPException(409, str(e))


@app.post("/api/filing/{fid}/skip")
def filing_skip(fid: int) -> dict:
    from harness import filing
    try:
        return _with_conn(lambda c: filing.skip(c, fid))
    except KeyError:
        raise HTTPException(404, "No such filing")
    except ValueError as e:
        raise HTTPException(409, str(e))


# --- Scanned invoices and receipts ---
class ScanEdit(BaseModel):
    doc_type: str | None = None
    supplier: str | None = None
    number: str | None = None
    amount: float | str | None = None
    currency: str | None = None
    doc_date: str | None = None
    paid_date: str | None = None
    folder: str | None = None


@app.get("/api/scans")
def scans_list() -> dict:
    from harness import audit, filing, scans
    def go(c):
        newly = scans.reconcile(c)
        return newly, scans.recent(c), scans.summary(c)
    newly, items, summary = _with_conn(go)
    from harness import suivi_export as SE
    docs = SE.read_state(DATA_DIR).get("docs", {})
    for it in items:                                                   # the Suivi journal row each filed document received
        it["journal_id"] = (docs.get(str(it["id"])) or {}).get("journal_id")
    if newly and audit.configured(audit.ROOT):                       # newly filed documents: re-run her checker so the tile includes them
        audit.start_background(db.connect, audit.ROOT, audit.years_available(audit.ROOT)[-1])
    return {"items": items, "summary": summary}


@app.get("/api/scans/summary")
def scans_summary() -> dict:
    from harness import scans
    return _with_conn(scans.summary)


@app.post("/api/scans/upload")
async def scans_upload(request: Request) -> dict:
    from urllib.parse import unquote
    from harness import filingspec, scans
    name, content = unquote(request.headers.get("x-filename", "document.pdf")), await request.body()
    if not content or len(content) > filingspec.MAX_BYTES:
        raise HTTPException(422, "Choose a PDF of at most 25 MB")
    if not content.startswith(b"%PDF"):
        raise HTTPException(422, "That file is not a PDF")
    def go(c):
        sid, new = scans.register(c, name, content, "upload")
        return sid, new
    sid, new = _with_conn(go)
    if new:
        threading.Thread(target=lambda: _read_now(sid), daemon=True).start()
    return {"id": sid, "new": new}


def _read_now(sid: int):
    from harness import scans
    c = db.connect()
    try:
        s = c.execute("SELECT status FROM scans WHERE id=?", (sid,)).fetchone()
        if s and s["status"] == "found":
            scans.read_scan(c, scans.Gateway(), sid)
    except Exception:
        pass
    finally:
        c.close()


@app.post("/api/scans/{sid}/edit")
def scans_edit(sid: int, body: ScanEdit) -> dict:
    from harness import scans
    try:
        return _with_conn(lambda c: scans.edit(c, sid, body.model_dump(exclude_unset=True)))
    except KeyError:
        raise HTTPException(404, "No such scan")
    except ValueError as e:
        raise HTTPException(422, str(e))


@app.post("/api/scans/{sid}/approve")
def scans_approve(sid: int) -> dict:
    from harness import scans
    try:
        return _with_conn(lambda c: scans.approve(c, sid))
    except KeyError:
        raise HTTPException(404, "No such scan")
    except ValueError as e:
        raise HTTPException(409, str(e))


@app.post("/api/scans/{sid}/skip")
def scans_skip(sid: int) -> dict:
    from harness import scans
    try:
        return _with_conn(lambda c: scans.skip(c, sid))
    except KeyError:
        raise HTTPException(404, "No such scan")
    except ValueError as e:
        raise HTTPException(409, str(e))


@app.post("/api/scans/{sid}/split")
def scans_split(sid: int) -> dict:
    from harness import scans
    try:
        return {"ids": _with_conn(lambda c: scans.split_pages(c, sid))}
    except KeyError:
        raise HTTPException(404, "No such scan")
    except ValueError as e:
        raise HTTPException(409, str(e))


class MergeIn(BaseModel):
    ids: list[int]


@app.post("/api/scans/merge")
def scans_merge(body: MergeIn) -> dict:
    from harness import scans
    try:
        return {"id": _with_conn(lambda c: scans.merge_scans(c, body.ids))}
    except KeyError:
        raise HTTPException(404, "No such scan")
    except ValueError as e:
        raise HTTPException(409, str(e))


@app.get("/api/scans/{sid}/image")
def scans_image(sid: int, page: int = 1, w: int = 700):
    from fastapi.responses import Response
    from harness import scans
    png = _with_conn(lambda c: scans.page_image(c, sid, page, w))
    if png is None:
        raise HTTPException(404, "No picture for this scan")
    return Response(png, media_type="image/png", headers={"Cache-Control": "private, max-age=3600"})


# --- Hours this week (from hours.csv, read-only) ---
@app.get("/api/hours")
def hours_week(day: str | None = None) -> dict:
    from datetime import date as _date
    from harness import hours
    from harness.config import now_local
    try:
        d = _date.fromisoformat(day) if day else None
    except ValueError:
        raise HTTPException(422, "day must look like 2026-09-30")
    return _with_conn(lambda c: hours.week_summary(c, now_local().date(), d))
