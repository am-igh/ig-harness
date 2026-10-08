"""The report workspace behind a reporting deadline: what the funder requires, the documents we hold for it, a TEMPLATE made by plain rules from the requirements and the harness's own facts
(no model), and working drafts that are saved as new versions (nothing is ever overwritten). Funder forms and submitted copies stay in her folders: only their location is kept here.
Personal items are never used."""
import sqlite3
from datetime import date, datetime

from harness import pm
from harness.config import now_local

KINDS = {"funder_form": "Funder's form", "template": "Template made from the requirements", "draft": "Working draft", "submitted": "Submitted copy", "other": "Other document"}
WORDS = {"summary": "about 1 to 2 pages", "standard": "about 4 to 6 pages", "detailed": "about 8 to 12 pages", "line-by-line": "every line item, with supporting detail"}
RULE_TYPES = ("overhead", "budget_approval", "procurement", "visibility")
FR = {"Summary of the period": "Résumé de la période", "Progress against the plan and results framework": "Avancement par rapport au plan et au cadre de résultats", "Activities carried out": "Activités menées",
      "Challenges, risks and how they were handled": "Difficultés, risques et mesures prises", "Partners": "Partenaires", "Lessons learned": "Enseignements tirés", "Plan for the next period": "Plan pour la période suivante",
      "Funds received in the period": "Fonds reçus pendant la période", "Expenditure by budget line": "Dépenses par ligne budgétaire", "Exchange rates": "Taux de change", "Explanation of variances": "Explication des écarts",
      "Supporting documents": "Pièces justificatives"}


def _row(conn, deadline_id: int):
    return conn.execute("SELECT d.*, o.canon, o.title AS otitle, o.clause, o.anchor, o.offset_days, o.recurrence, o.fixed_date, o.format, o.language, o.detail, o.note AS onote, o.contract_id, "
                        "c.title AS ctitle, c.amount, c.currency, c.budget_rate, c.start_date AS cstart, c.end_date AS cend, c.project_id, f.name AS funder_name, f.short AS funder, f.contact, p.code, p.name AS pname "
                        "FROM pm_deadlines d JOIN pm_obligations o ON o.id = d.obligation_id JOIN pm_contracts c ON c.id = o.contract_id JOIN pm_funders f ON f.id = c.funder_id JOIN pm_projects p ON p.id = c.project_id "
                        "WHERE d.id = ?", (deadline_id,)).fetchone()


def _doc(r, with_content: bool = False) -> dict:
    out = {"id": r["id"], "deadline_id": r["deadline_id"], "kind": r["kind"], "kind_label": KINDS[r["kind"]], "title": r["title"], "version": r["version"], "file_path": r["file_path"], "note": r["note"], "author": r["author"], "created_at": r["created_at"]}
    if with_content:
        out["content"] = r["content"]
    return out


def documents(conn, deadline_id: int) -> list[dict]:
    """The newest version of each document, with how many versions exist."""
    out = []
    for r in conn.execute("SELECT d.* FROM pm_documents d WHERE d.deadline_id = ? AND d.version = (SELECT MAX(version) FROM pm_documents x WHERE x.deadline_id = d.deadline_id AND x.kind = d.kind AND x.title = d.title) "
                          "ORDER BY CASE d.kind WHEN 'funder_form' THEN 0 WHEN 'template' THEN 1 WHEN 'draft' THEN 2 WHEN 'submitted' THEN 3 ELSE 4 END, d.title", (deadline_id,)):
        n = conn.execute("SELECT COUNT(*) FROM pm_documents WHERE deadline_id = ? AND kind = ? AND title = ?", (deadline_id, r["kind"], r["title"])).fetchone()[0]
        out.append({**_doc(r, with_content=True), "versions": n})
    return out


def versions(conn, doc_id: int) -> list[dict]:
    r = conn.execute("SELECT * FROM pm_documents WHERE id = ?", (doc_id,)).fetchone()
    if r is None:
        return []
    return [_doc(x, with_content=True) for x in conn.execute("SELECT * FROM pm_documents WHERE deadline_id = ? AND kind = ? AND title = ? ORDER BY version DESC", (r["deadline_id"], r["kind"], r["title"]))]


def _add(conn, deadline_id: int, kind: str, title: str, content=None, file_path=None, note=None, author="you", now: datetime | None = None) -> int:
    v = (conn.execute("SELECT MAX(version) FROM pm_documents WHERE deadline_id = ? AND kind = ? AND title = ?", (deadline_id, kind, title)).fetchone()[0] or 0) + 1
    cur = conn.execute("INSERT INTO pm_documents (deadline_id, kind, title, version, content, file_path, note, author, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
                       (deadline_id, kind, title, v, content, file_path, note, author, (now or now_local()).isoformat(timespec="seconds")))
    conn.commit()
    return cur.lastrowid


def attach_reference(conn, deadline_id: int, kind: str, title: str, file_path: str, note: str | None = None, now=None) -> int:
    """A funder's form, a submitted copy or another document that stays in her folders: only where it is kept is recorded."""
    if kind not in ("funder_form", "submitted", "other"):
        raise pm.PMError("A reference can be a funder's form, a submitted copy or another document")
    if _row(conn, deadline_id) is None:
        raise pm.PMError("Unknown deadline")
    if not (title or "").strip() or not (file_path or "").strip():
        raise pm.PMError("Give a title and where the document is kept")
    return _add(conn, deadline_id, kind, title.strip(), file_path=file_path.strip(), note=note, now=now)


# ---------------------------------------------------------------- the harness's own facts for the period
def facts(conn, d) -> dict:
    a, b = d["period_start"], d["period_end"]
    lo, hi = (a, b) if a and b else (d["cstart"] or "0000-00-00", d["cend"] or "9999-12-31")
    tr = [dict(t) for t in conn.execute("SELECT received_date, received_amount, chf_received, bank_rate, label FROM pm_transfers WHERE contract_id = ? AND received_date BETWEEN ? AND ? ORDER BY received_date", (d["contract_id"], lo, hi))]
    journal = [dict(r) for r in conn.execute("SELECT entry_date, text FROM journal_entries WHERE project_code = ? AND space = 'work' AND entry_date BETWEEN ? AND ? ORDER BY entry_date LIMIT 25", (d["code"], lo, hi))]
    tasks = [r["title"] for r in conn.execute("SELECT title FROM tasks WHERE project_code = ? AND space = 'work' AND status = 'done' AND substr(done_at,1,10) BETWEEN ? AND ? ORDER BY done_at LIMIT 25", (d["code"], lo, hi))]
    hours = conn.execute("SELECT COALESCE(SUM(hours), 0) FROM hours WHERE project = ? AND date BETWEEN ? AND ?", (d["code"], lo, hi)).fetchone()[0]
    rules = [{"canon": r["canon"], "title": r["title"], "clause": r["clause"]} for r in conn.execute("SELECT canon, title, clause FROM pm_obligations WHERE contract_id = ? AND canon IN (%s)" % ",".join("?" * len(RULE_TYPES)), (d["contract_id"], *RULE_TYPES))]
    return {"transfers": tr, "journal": journal, "tasks": tasks, "hours": round(hours, 1), "rules": rules}


def workspace(conn, deadline_id: int, today: date | None = None) -> dict | None:
    today = today or now_local().date()
    d = _row(conn, deadline_id)
    if d is None:
        return None
    left = (date.fromisoformat(d["due_date"]) - today).days
    ob = {"title": d["otitle"], "clause": d["clause"], "rule": pm.rule_label(d), "language": d["language"], "format": d["format"], "detail": d["detail"], "note": d["onote"], "canon": d["canon"], "canon_label": pm.CANON[d["canon"]]}
    return {"deadline": {"id": d["id"], "title": d["otitle"], "period": d["period_label"], "period_start": d["period_start"], "period_end": d["period_end"], "due_date": d["due_date"], "status": d["status"], "days_left": left,
                         "submitted_on": d["submitted_on"], "funder": d["funder"], "funder_name": d["funder_name"], "contact": d["contact"], "project": d["pname"], "code": d["code"], "project_id": d["project_id"], "contract": d["ctitle"]},
            "requirement": ob, "rules": facts(conn, d)["rules"], "documents": documents(conn, deadline_id), "has_template": any(x["kind"] == "template" for x in documents(conn, deadline_id))}


# ---------------------------------------------------------------- the template (plain rules)
def _h(d, text: str) -> str:
    lang = (d["language"] or "").split(",")[0].strip()
    return FR.get(text, text) if lang == "fr" else text


def _money(n, cur="CHF") -> str:
    return f"{n:,.2f} {cur}"


def build_template(conn, deadline_id: int) -> tuple[str, str]:
    d = _row(conn, deadline_id)
    if d is None:
        raise pm.PMError("Unknown deadline")
    f = facts(conn, d)
    lang = d["language"] or "not specified"
    when = f"{d['period_start']} to {d['period_end']}" if d["period_start"] else (f"{d['cstart']} to {d['cend']}" if d["cstart"] else "whole contract")
    head = [f"# {d['otitle']}: {d['funder_name']}", "",
            f"**Project:** {d['pname']} ({d['code']})  ·  **Contract:** {d['ctitle']}  ·  **Period covered:** {when}  ·  **Due:** {d['due_date']}",
            f"**Language:** {lang}  ·  **Format:** {d['format'] or 'free form'}  ·  **Level of detail:** {d['detail'] or 'not specified'}" + (f" ({WORDS[d['detail']]})" if d["detail"] in WORDS else ""),
            f"**Requirement:** {d['clause'] or 'clause not recorded'}, {pm.rule_label(d)}" + (f"  ·  {d['onote']}" if d["onote"] else ""), ""]
    if f["rules"]:
        head += ["**Rules of this contract to respect:**"] + [f"- {r['title']}" + (f" ({r['clause']})" if r["clause"] else "") for r in f["rules"]] + [""]
    H = lambda t: f"## {_h(d, t)}"
    body: list[str] = []
    c = d["canon"]
    if c == "narrative_report":
        body += [H("Summary of the period"), "", "_Three or four sentences a busy reader could stop after._", "", H("Progress against the plan and results framework"), "",
                 "| Result or indicator | Target | Achieved in the period | Cumulative | Comment |", "|---|---|---|---|---|", "| | | | | |", "",
                 H("Activities carried out"), "", H("Challenges, risks and how they were handled"), "", H("Partners"), "", H("Lessons learned"), "", H("Plan for the next period"), ""]
    elif c == "financial_report":
        body += [H("Funds received in the period"), "", "| Date | Transfer | Amount | Bank rate | CHF credited |", "|---|---|---|---|---|"]
        body += [f"| {t['received_date']} | {t['label']} | {_money(t['received_amount'], d['currency'])} | {t['bank_rate']} | {_money(t['chf_received'])} |" for t in f["transfers"]] or ["| | | | | |"]
        body += ["", H("Expenditure by budget line"), "", f"| Budget line | Budget ({d['currency']}) | This period | Cumulative | Balance | Variance % |", "|---|---|---|---|---|---|", "| | | | | | |", "",
                 H("Exchange rates"), "", f"Budget rate in the contract: {d['budget_rate']} CHF per 1 {d['currency']}. Rates used are those the bank assigned when each transfer arrived." if d["currency"] != "CHF" else "The contract is in CHF: no exchange rate applies.", "",
                 H("Explanation of variances"), "", H("Supporting documents"), "", "_List invoices, receipts, bank statements and contracts, with their file names._", ""]
    elif c == "milestone_report":
        body += ["## Milestone and deliverable", "", "## Evidence the funder can verify", "", "- [ ] The deliverable itself", "- [ ] Proof of use or adoption", "- [ ] A short note on what changed", "", "## Result achieved and who benefited", "", "## Request for the milestone payment", ""]
    elif c == "audit":
        body += ["## Audit checklist", "", "- [ ] Auditor engaged and scope agreed in writing", "- [ ] General ledger and trial balance for the period", "- [ ] Bank statements for every account used", "- [ ] Contracts, amendments and sub-grant agreements",
                 "- [ ] Procurement files (quotes, selection notes)", "- [ ] Partner reports and receipts", "- [ ] Management representation letter signed", "", "## Timetable", "", f"Final report due {d['due_date']}.", ""]
    elif c == "partner_report":
        body += ["## What the partner must send", "", "- [ ] Activity report for the period", "- [ ] Expenditure by budget line, with receipts", "- [ ] Exchange rates and bank fees on payments received", "- [ ] Photos or other evidence of activities", "",
                 "## Our review notes", "", "## Questions back to the partner", ""]
    else:
        body += [f"## {d['otitle']}", "", "To: " + (d["contact"] or "the funder's contact"), "", "_Short text covering what the clause asks us to declare or notify._", ""]
    foot = ["---", "", "### From the harness (check before using)", ""]
    foot += [f"- **Hours logged on {d['code']} in the period:** {f['hours']}"] if f["hours"] else []
    foot += (["- **Completed tasks:**"] + [f"  - {t}" for t in f["tasks"]]) if f["tasks"] else ["- No completed tasks recorded for this period."]
    foot += (["- **Journal entries:**"] + [f"  - {j['entry_date']}: {j['text']}" for j in f["journal"]]) if f["journal"] else ["- No journal entries recorded for this period."]
    foot += ["", "_This template was made by rules from the requirement and the harness's own records. It is a starting point, not a finished report._"]
    return f"Template: {d['otitle']} ({d['period_label']})", "\n".join(head + body + foot)


def make_template(conn, deadline_id: int, now=None) -> dict:
    title, content = build_template(conn, deadline_id)
    did = _add(conn, deadline_id, "template", title, content=content, author="rules", now=now)
    return _doc(conn.execute("SELECT * FROM pm_documents WHERE id = ?", (did,)).fetchone(), with_content=True)


def start_draft(conn, deadline_id: int, now=None) -> dict:
    tpl = next((x for x in documents(conn, deadline_id) if x["kind"] == "template"), None)
    d = _row(conn, deadline_id)
    if tpl is None:
        raise pm.PMError("There is no template yet: create one first")
    title = f"Draft: {d['otitle']} ({d['period_label']})"
    if conn.execute("SELECT 1 FROM pm_documents WHERE deadline_id = ? AND kind = 'draft' AND title = ?", (deadline_id, title)).fetchone():
        raise pm.PMError("A draft already exists: open it and save a new version")
    did = _add(conn, deadline_id, "draft", title, content=tpl["content"], note="Started from the template", author="you", now=now)
    if d["status"] == "todo":
        pm.set_deadline_status(conn, deadline_id, "drafting")
    return _doc(conn.execute("SELECT * FROM pm_documents WHERE id = ?", (did,)).fetchone(), with_content=True)


def save_version(conn, doc_id: int, content: str, now=None) -> dict:
    r = conn.execute("SELECT * FROM pm_documents WHERE id = ?", (doc_id,)).fetchone()
    if r is None:
        raise pm.PMError("No such document")
    if r["kind"] != "draft":
        raise pm.PMError("Only a working draft can be edited. Start a draft from the template.")
    if not (content or "").strip():
        raise pm.PMError("The draft is empty")
    latest = conn.execute("SELECT MAX(version) FROM pm_documents WHERE deadline_id = ? AND kind = 'draft' AND title = ?", (r["deadline_id"], r["title"])).fetchone()[0]
    if r["version"] != latest:
        raise pm.PMError("A newer version exists: open the newest one")
    did = _add(conn, r["deadline_id"], "draft", r["title"], content=content, author="you", now=now)
    d = conn.execute("SELECT status FROM pm_deadlines WHERE id = ?", (r["deadline_id"],)).fetchone()
    if d["status"] == "todo":
        pm.set_deadline_status(conn, r["deadline_id"], "drafting")
    return _doc(conn.execute("SELECT * FROM pm_documents WHERE id = ?", (did,)).fetchone(), with_content=True)


def get_document(conn, doc_id: int) -> dict | None:
    r = conn.execute("SELECT * FROM pm_documents WHERE id = ?", (doc_id,)).fetchone()
    return _doc(r, with_content=True) if r else None
