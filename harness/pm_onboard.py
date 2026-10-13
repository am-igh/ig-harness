"""Contract onboarding: collect, in a few guided steps, everything a contract can contain (parties and dates, money and instalments, reports and their deadlines, rules such as overhead cap and
prior approval, other terms and contacts), show exactly what will be created, and create it as ONE step (all or nothing). Plain rules; no model reads anything. The signed contract stays in her folders:
only its location is recorded. Anything left blank is simply not created; the warnings say what is missing so she can add it later."""
import re
from datetime import date, timedelta

from harness import pm

# Common reporting duties: picking one fills in typical settings she can change. (id, label, canon, recurrence, anchor, offset_days, detail, language-note)
PRESETS = [
    {"id": "narrative_annual", "label": "Annual narrative report", "canon": "narrative_report", "recurrence": "annual", "anchor": "period_end", "offset_days": 60, "detail": "standard"},
    {"id": "narrative_semiannual", "label": "Six-monthly narrative or results report", "canon": "narrative_report", "recurrence": "semiannual", "anchor": "period_end", "offset_days": 30, "detail": "standard"},
    {"id": "narrative_quarterly", "label": "Quarterly narrative report", "canon": "narrative_report", "recurrence": "quarterly", "anchor": "period_end", "offset_days": 30, "detail": "standard"},
    {"id": "financial_quarterly", "label": "Quarterly financial report", "canon": "financial_report", "recurrence": "quarterly", "anchor": "period_end", "offset_days": 30, "detail": "detailed"},
    {"id": "financial_semiannual", "label": "Six-monthly financial report", "canon": "financial_report", "recurrence": "semiannual", "anchor": "period_end", "offset_days": 30, "detail": "standard"},
    {"id": "financial_annual", "label": "Annual financial report", "canon": "financial_report", "recurrence": "annual", "anchor": "period_end", "offset_days": 90, "detail": "standard"},
    {"id": "final_narrative", "label": "Final narrative report", "canon": "narrative_report", "recurrence": "once", "anchor": "end", "offset_days": 60, "detail": "detailed"},
    {"id": "final_financial", "label": "Final financial report", "canon": "financial_report", "recurrence": "once", "anchor": "end", "offset_days": 90, "detail": "detailed"},
    {"id": "audit_final", "label": "External audit at the end", "canon": "audit", "recurrence": "once", "anchor": "end", "offset_days": 120, "detail": "line-by-line"},
    {"id": "audit_annual", "label": "Annual audit (when spending passes a threshold)", "canon": "audit", "recurrence": "annual", "anchor": "period_end", "offset_days": 120, "detail": "line-by-line"},
    {"id": "milestone", "label": "Milestone report (on a fixed date)", "canon": "milestone_report", "recurrence": "once", "anchor": "fixed", "offset_days": 0, "detail": "standard"},
    {"id": "notification", "label": "Declaration or notification (on a fixed date)", "canon": "notification", "recurrence": "once", "anchor": "fixed", "offset_days": 0, "detail": "summary"},
    {"id": "partner_quarterly", "label": "Partner report to us (quarterly)", "canon": "partner_report", "recurrence": "quarterly", "anchor": "period_end", "offset_days": 15, "detail": "standard"},
]
KINDS = ("grant", "subgrant")
MAX_PAYMENTS, MAX_REPORTS = 60, 40
_ISO = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def options(conn) -> dict:
    return {"presets": PRESETS, "canon": pm.CANON, "detail": pm.DETAIL, "kinds": list(KINDS),
            "projects": [{"id": r["id"], "code": r["code"], "name": r["name"], "start_date": r["start_date"], "end_date": r["end_date"]} for r in conn.execute("SELECT id, code, name, start_date, end_date FROM pm_projects ORDER BY code")],
            "funders": pm.funders(conn)}


def _num(v):
    if v in (None, ""):
        return None
    try:
        return float(str(v).replace(",", ".").replace("'", ""))
    except ValueError:
        return "bad"


def _date(v, what, errors, required=False):
    if not v:
        if required:
            errors.append(f"{what} is required")
        return None
    if not _ISO.match(str(v)):
        errors.append(f"{what} is not a valid date")
        return None
    try:
        return date.fromisoformat(v)
    except ValueError:
        errors.append(f"{what} is not a valid date")
        return None


def _rules(data: dict, cur: str) -> list[dict]:
    """The rule-type obligations implied by the rules step (no deadlines: they are ongoing)."""
    r = data.get("rules") or {}
    out = []
    pct = _num(r.get("overhead_pct"))
    if pct not in (None, "bad") and pct > 0:
        out.append({"canon": "overhead", "title": f"Overhead capped at {pct:g}%", "clause": r.get("overhead_clause") or None})
    pct = _num(r.get("approval_pct"))
    if pct not in (None, "bad") and pct > 0:
        out.append({"canon": "budget_approval", "title": f"Prior written approval for reallocations above {pct:g}% of a budget line", "clause": r.get("approval_clause") or None})
    thr, quotes = _num(r.get("procurement_threshold")), _num(r.get("procurement_quotes"))
    if thr not in (None, "bad") and thr > 0:
        n = int(quotes) if quotes not in (None, "bad") and quotes > 0 else 3
        out.append({"canon": "procurement", "title": f"{n} written quotes above {cur} {thr:,.0f}", "clause": r.get("procurement_clause") or None})
    vis = (r.get("visibility") or "").strip()
    if vis:
        out.append({"canon": "visibility", "title": vis[:200], "clause": r.get("visibility_clause") or None, "language": r.get("visibility_language") or None})
    return out


def _normalise(data: dict) -> dict:
    c = dict(data.get("contract") or {})
    c["currency"] = (c.get("currency") or "CHF").strip().upper()[:3]
    return c


def validate(conn, data: dict) -> dict:
    errors, warnings = [], []
    c = _normalise(data)
    cur = c["currency"]
    # who
    p, f = data.get("project") or {}, data.get("funder") or {}
    if p.get("mode") == "new":
        code = re.sub(r"[^A-Z0-9]", "", (p.get("code") or "").upper())
        if not code:
            errors.append("The new project needs a code")
        elif conn.execute("SELECT 1 FROM pm_projects WHERE code = ?", (code,)).fetchone():
            errors.append(f"{code} is already a project")
        if not (p.get("name") or "").strip():
            errors.append("The new project needs a name")
    elif conn.execute("SELECT 1 FROM pm_projects WHERE id = ?", (p.get("id"),)).fetchone() is None:
        errors.append("Choose the project this contract belongs to")
    if f.get("mode") == "new":
        if not (f.get("name") or "").strip():
            errors.append("The new funder or partner needs a name")
        elif conn.execute("SELECT 1 FROM pm_funders WHERE name = ?", (f["name"].strip(),)).fetchone():
            errors.append(f"“{f['name'].strip()}” is already in the list: choose it instead of adding it again")
    elif conn.execute("SELECT 1 FROM pm_funders WHERE id = ?", (f.get("id"),)).fetchone() is None:
        errors.append("Choose the funder or partner")
    # the contract
    if not (c.get("title") or "").strip():
        errors.append("The contract needs a title")
    if c.get("kind", "grant") not in KINDS:
        errors.append("The contract is a grant (money in) or a sub-grant (money out)")
    if not re.fullmatch(r"[A-Z]{3}", cur):
        errors.append("The currency must be a three-letter code such as CHF")
    amount = _num(c.get("amount"))
    if amount == "bad" or amount is None or amount <= 0:
        errors.append("Enter the contract amount (a positive number)")
        amount = None
    rate = _num(c.get("budget_rate"))
    if cur != "CHF" and (rate in (None, "bad") or rate <= 0):
        errors.append(f"A contract in {cur} needs the budget exchange rate (CHF per 1 {cur})")
    signed, start, end = _date(c.get("signed_date"), "The signing date", errors), _date(c.get("start_date"), "The start date", errors), _date(c.get("end_date"), "The end date", errors)
    if start and end and end < start:
        errors.append("The end date is before the start date")
    if signed and start and signed > start + timedelta(days=366):
        warnings.append("The contract was signed long before it starts: check the dates")
    if not c.get("file_path"):
        warnings.append("No location for the signed contract: add where it is kept so it can be found later")
    # payments
    pays = data.get("payments") or []
    if len(pays) > MAX_PAYMENTS:
        errors.append(f"At most {MAX_PAYMENTS} payments")
    total = 0.0
    for i, pay in enumerate(pays[:MAX_PAYMENTS], 1):
        if not (pay.get("label") or "").strip():
            errors.append(f"Payment {i} needs a label")
        d = _date(pay.get("expected_date"), f"The date of payment {i}", errors, required=True)
        a = _num(pay.get("expected_amount"))
        if a in (None, "bad") or a <= 0:
            errors.append(f"Payment {i} needs a positive amount")
        else:
            total += a
        if d and start and end and not (start - timedelta(days=60) <= d <= end + timedelta(days=366)):
            warnings.append(f"Payment {i} falls well outside the contract period")
    if pays and amount and abs(total - amount) > max(1.0, 0.005 * amount):
        warnings.append(f"The payments add up to {cur} {total:,.2f}, not the contract amount of {cur} {amount:,.2f}")
    if not pays:
        warnings.append("No payment schedule: the expected money will not be tracked until you add it")
    # reports
    reps = data.get("reports") or []
    if len(reps) > MAX_REPORTS:
        errors.append(f"At most {MAX_REPORTS} reporting requirements")
    for i, r in enumerate(reps[:MAX_REPORTS], 1):
        label = (r.get("title") or f"Requirement {i}").strip()
        if r.get("canon") not in pm.CANON:
            errors.append(f"“{label}”: choose what kind of requirement it is")
        if not (r.get("title") or "").strip():
            errors.append(f"Requirement {i} needs a title")
        rec, anc = r.get("recurrence", "once"), r.get("anchor", "period_end")
        if rec not in ("none", "once", "quarterly", "semiannual", "annual"):
            errors.append(f"“{label}”: unknown frequency")
        if rec in pm.STEP and anc != "period_end":
            errors.append(f"“{label}”: a repeating report is due after the end of each period")
        if rec in pm.STEP and not (start and end):
            errors.append(f"“{label}” repeats, so the contract needs both a start and an end date")
        if rec == "once" and anc in ("end", "start") and not (end if anc == "end" else start):
            errors.append(f"“{label}” is counted from the contract {'end' if anc == 'end' else 'start'}, which has no date yet")
        if anc == "fixed":
            fd = _date(r.get("fixed_date"), f"The date of “{label}”", errors, required=True)
            if fd and start and end and not (start <= fd <= end + timedelta(days=366)):
                warnings.append(f"“{label}” is due outside the contract period")
        off = _num(r.get("offset_days"))
        if off == "bad" or (off is not None and not 0 <= off <= 730):
            errors.append(f"“{label}”: the number of days must be between 0 and 730")
        if r.get("detail") and r["detail"] not in pm.DETAIL:
            errors.append(f"“{label}”: unknown level of detail")
    if not reps:
        warnings.append("No reporting requirements yet: no deadlines will be created")
    # rules
    for key, what in (("overhead_pct", "The overhead cap"), ("approval_pct", "The approval threshold")):
        v = _num((data.get("rules") or {}).get(key))
        if v == "bad" or (v is not None and not 0 < v <= 100):
            errors.append(f"{what} must be a percentage between 0 and 100")
    for key, what in (("procurement_threshold", "The procurement threshold"), ("procurement_quotes", "The number of quotes")):
        if _num((data.get("rules") or {}).get(key)) == "bad":
            errors.append(f"{what} must be a number")
    # terms
    t = data.get("terms") or {}
    n = _num(t.get("termination_notice_days"))
    if n == "bad" or (n is not None and not 0 <= n <= 1000):
        errors.append("The notice period must be a number of days")
    for ct in t.get("contacts") or []:
        if (ct.get("email") or "") and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", ct["email"]):
            errors.append(f"“{ct['email']}” is not a valid email address")
    if not (t.get("contacts") or []):
        warnings.append("No contact person recorded for this contract")
    if conn.execute("SELECT 1 FROM pm_contracts k JOIN pm_projects p ON p.id = k.project_id WHERE p.id = ? AND k.funder_id = ? AND lower(k.title) = lower(?)",
                    (p.get("id"), f.get("id"), (c.get("title") or ""))).fetchone() and p.get("mode") != "new" and f.get("mode") != "new":
        warnings.append("A contract with this title already exists for this project and funder")
    return {"errors": errors, "warnings": warnings}


def preview(conn, data: dict) -> dict:
    """What would be created, without creating anything: the checks, the counts and the deadlines."""
    v = validate(conn, data)
    c = _normalise(data)
    cur, start, end = c["currency"], c.get("start_date"), c.get("end_date")
    funder = (data.get("funder") or {})
    short = (funder.get("short") or funder.get("name") or "")
    if funder.get("mode") != "new":
        r = conn.execute("SELECT short FROM pm_funders WHERE id = ?", (funder.get("id"),)).fetchone()
        short = r["short"] if r else short
    deadlines, reqs = [], []
    for r in data.get("reports") or []:
        if r.get("canon") not in pm.CANON or not (r.get("title") or "").strip():
            continue
        try:
            sch = pm.schedule(r.get("recurrence", "once"), r.get("anchor", "period_end"), int(float(r.get("offset_days") or 0)), r.get("fixed_date"), start, end)
        except (ValueError, TypeError, KeyError):
            sch = []
        reqs.append({"title": r["title"], "canon": pm.CANON[r["canon"]], "deadlines": len(sch)})
        deadlines += [{"title": r["title"], "period": lab if lab not in ("fixed date", "final", "start") else "", "due_date": d.isoformat()} for lab, d, _, _ in sch]
    deadlines.sort(key=lambda x: x["due_date"])
    rules = [x["title"] for x in _rules(data, cur)]
    pays = [p for p in (data.get("payments") or []) if p.get("expected_date")]
    return {**v, "summary": {"funder": short, "requirements": len(reqs), "deadlines": len(deadlines), "rules": len(rules), "payments": len(pays)},
            "requirements": reqs, "deadlines": deadlines[:14], "more_deadlines": max(0, len(deadlines) - 14), "rules": rules,
            "payments": [{"label": p.get("label"), "date": p.get("expected_date"), "amount": p.get("expected_amount"), "condition": p.get("condition")} for p in pays]}


def create(conn, data: dict) -> dict:
    """Create everything, or nothing: any problem undoes it all. Returns what was created."""
    v = validate(conn, data)
    if v["errors"]:
        raise pm.PMError("; ".join(v["errors"]))
    c = _normalise(data)
    cur = c["currency"]
    p, f, t = data["project"], data["funder"], dict(data.get("terms") or {})
    kind = c.get("kind", "grant")
    n_deadlines = 0
    with pm.batch(conn):
        if p.get("mode") == "new":
            pid = pm.add_project(conn, p["code"], p["name"], p.get("start_date") or c.get("start_date"), p.get("end_date") or c.get("end_date"), p.get("lead") or None, p.get("summary") or None)
        else:
            pid = p["id"]
        if f.get("mode") == "new":
            contacts = t.get("contacts") or []
            fid = pm.add_funder(conn, f["name"].strip(), (f.get("short") or "").strip() or None, f.get("role") or ("partner" if kind == "subgrant" else "funder"), f.get("currency") or cur,
                                f.get("contact") or (contacts[0].get("name") if contacts else None))
        else:
            fid = f["id"]
        terms = {k: v_ for k, v_ in {"termination_notice_days": _num(t.get("termination_notice_days")), "governing_law": t.get("governing_law"), "ownership": t.get("ownership"),
                                      "data_protection": t.get("data_protection"), "special_conditions": t.get("special_conditions"), "eligible_costs": (data.get("rules") or {}).get("eligible_costs"),
                                      "contacts": [ct for ct in (t.get("contacts") or []) if (ct.get("name") or ct.get("email"))]}.items() if v_ not in (None, "", [])}
        kid = pm.add_contract(conn, pid, fid, c["title"].strip(), kind=kind, amount=_num(c.get("amount")), currency=cur, budget_rate=_num(c.get("budget_rate")), signed_date=c.get("signed_date") or None,
                              start_date=c.get("start_date") or None, end_date=c.get("end_date") or None, file_path=c.get("file_path") or None, summary=(c.get("summary") or None),
                              reference=(c.get("reference") or None), terms=terms or None)
        n_obl = 0
        for r in data.get("reports") or []:
            oid = pm.add_obligation(conn, kid, r["canon"], r["title"].strip(), clause=r.get("clause") or None, anchor=r.get("anchor", "period_end") if r.get("recurrence", "once") != "none" else "none",
                                    offset_days=int(float(r.get("offset_days") or 0)), recurrence=r.get("recurrence", "once"), fixed_date=r.get("fixed_date") or None, format=r.get("format") or None,
                                    language=r.get("language") or None, detail=r.get("detail") or None, note=r.get("note") or None)
            n_deadlines += conn.execute("SELECT COUNT(*) FROM pm_deadlines WHERE obligation_id = ?", (oid,)).fetchone()[0]
            n_obl += 1
        for rule in _rules(data, cur):
            pm.add_obligation(conn, kid, rule["canon"], rule["title"], clause=rule.get("clause"), anchor="none", recurrence="none", language=rule.get("language"))
            n_obl += 1
        n_pay = 0
        if kind == "grant":
            for pay in data.get("payments") or []:
                pm.add_transfer(conn, kid, pay["label"].strip(), expected_date=pay["expected_date"], expected_amount=_num(pay["expected_amount"]), note=(pay.get("condition") or None))
                n_pay += 1
    pm.sync_core(conn)
    return {"project_id": pid, "funder_id": fid, "contract_id": kid, "obligations": n_obl, "deadlines": n_deadlines, "payments": n_pay, "warnings": v["warnings"]}
