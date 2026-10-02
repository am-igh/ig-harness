"""Project checks: the harness's own `controle_projets` (her folder has no such script). Read-only; it looks at what the importers mirrored from
hours.csv, costs.csv and the register, and lists what is missing or off, in plain language. Same spirit as her audit checker: evidence for every
hour and every cost, dates, known projects and budget lines, and mandate details that are still empty."""
import sqlite3
from datetime import date, timedelta

from harness.hours import LATE_DAYS

SEV = {"error": 0, "warning": 1, "info": 2}


def _f(findings, area, severity, message, code=None, n=1, refs=None):
    findings.append({"area": area, "severity": severity, "code": code, "message": message, "count": n, "refs": (refs or [])[:5]})


def check_hours(conn, findings, known: set[str], lines: dict[str, set[str]], mandates: dict[str, dict]):
    rows = conn.execute("SELECT * FROM hours ORDER BY date").fetchall()
    def grp(pred, area_msg, sev, only_known=False):
        bad = [r for r in rows if pred(r)]
        if bad:
            _f(findings, "hours", sev, area_msg, n=len(bad), refs=[f"{r['date']} {r['project'] or '?'}" for r in bad])
    grp(lambda r: not (r["evidence"] or "").strip(), "Hours without an evidence pointer", "error")
    grp(lambda r: not r["entered_on"], "Hours without an entered_on date", "error")
    grp(lambda r: r["entered_on"] and (date.fromisoformat(r["entered_on"]) - date.fromisoformat(r["date"])).days > LATE_DAYS, f"Hours entered more than {LATE_DAYS} days after the day they are for", "warning")
    grp(lambda r: not r["hours"] or r["hours"] <= 0, "Hours entries with zero or missing hours", "error")
    grp(lambda r: not r["project"], "Hours entries without a project", "error")
    grp(lambda r: r["project"] and known and r["project"] not in known, "Hours for a project code that Suivi's Codes sheet does not know", "error")
    grp(lambda r: r["project"] in lines and lines[r["project"]] and r["budget_line"] and r["budget_line"] not in lines[r["project"]], "Hours charged to a budget line that is not in the register's Budget sheet", "warning")
    grp(lambda r: r["project"] in lines and lines[r["project"]] and not r["budget_line"], "Hours without a budget line, for a project that has budget lines", "warning")
    seen, dup = set(), []
    for r in rows:
        k = (r["date"], r["project"], r["description"])
        if k in seen:
            dup.append(r)
        seen.add(k)
    if dup:
        _f(findings, "hours", "warning", "The same hours entry appears twice (same day, project and description)", n=len(dup), refs=[f"{r['date']} {r['project']}" for r in dup])
    out_of = [r for r in rows if r["project"] in mandates and ((mandates[r["project"]]["activity_start"] and r["date"] < mandates[r["project"]]["activity_start"])
                                                               or (mandates[r["project"]]["activity_end"] and r["date"] > mandates[r["project"]]["activity_end"]))]
    if out_of:
        _f(findings, "hours", "warning", "Hours outside the mandate's activity period", n=len(out_of), refs=[f"{r['date']} {r['project']}" for r in out_of])
    return len(rows)


def check_costs(conn, findings, known: set[str], lines: dict[str, set[str]]):
    rows = conn.execute("SELECT * FROM costs ORDER BY date").fetchall()
    def grp(pred, msg, sev):
        bad = [r for r in rows if pred(r)]
        if bad:
            _f(findings, "costs", sev, msg, n=len(bad), refs=[f"{r['date'] or '?'} {r['supplier'] or '?'}" for r in bad])
    grp(lambda r: not (r["justificatif"] or "").strip(), "Costs without a justificatif (supporting document)", "error")
    grp(lambda r: r["currency"] and r["currency"] != "CHF" and r["amount_chf"] is None, "Costs in another currency without the CHF amount", "error")
    grp(lambda r: not r["payment_date"], "Costs without a payment date", "warning")
    grp(lambda r: not (r["invoice_reference"] or "").strip(), "Costs without an invoice reference", "warning")
    grp(lambda r: not r["project"] or (known and r["project"] not in known), "Costs for a missing or unknown project code", "error")
    grp(lambda r: r["project"] in lines and lines[r["project"]] and r["budget_line"] not in lines[r["project"]], "Costs charged to a budget line that is not in the register's Budget sheet", "warning")
    grp(lambda r: not r["entered_on"], "Costs without an entered_on date", "warning")
    return len(rows)


def check_mandates(conn, findings, today: date):
    rows = conn.execute("SELECT * FROM register_mandates ORDER BY code").fetchall()
    for m in rows:
        missing = [lab for col, lab in (("funder", "funder"), ("signature", "signature date"), ("activity_start", "activity start"), ("activity_end", "activity end"), ("reporting_deadline", "reporting deadline"), ("status", "status")) if not m[col]]
        if missing:
            _f(findings, "mandates", "warning", f"Mandate details still empty: {', '.join(missing)}", code=m["code"])
        active = (m["status"] or "").lower() not in ("closed", "clos", "terminated", "terminé")
        if m["activity_end"] and m["activity_end"] < today.isoformat() and active:
            _f(findings, "mandates", "warning", f"The activity period ended on {m['activity_end']} but the mandate is still '{m['status'] or 'open'}'", code=m["code"])
        if m["reporting_deadline"] and active and (m["close_out_state"] or "").lower() not in ("done", "closed", "submitted", "approved"):
            d = (date.fromisoformat(m["reporting_deadline"]) - today).days
            if d < 0:
                _f(findings, "mandates", "error", f"The reporting deadline ({m['reporting_deadline']}) passed {-d} days ago", code=m["code"])
            elif d <= 30:
                _f(findings, "mandates", "warning", f"The reporting deadline ({m['reporting_deadline']}) is in {d} days", code=m["code"])
    return len(rows)


def build_checks(conn: sqlite3.Connection, today: date) -> dict:
    findings: list[dict] = []
    known = {r[0] for r in conn.execute("SELECT code FROM project_codes")}
    lines: dict[str, set[str]] = {}
    for r in conn.execute("SELECT code, budget_line FROM register_budget"):
        lines.setdefault(r["code"], set()).add(r["budget_line"])
    mandates = {r["code"]: dict(r) for r in conn.execute("SELECT * FROM register_mandates")}
    n_hours = check_hours(conn, findings, known, lines, mandates)
    n_costs = check_costs(conn, findings, known, lines)
    n_mand = check_mandates(conn, findings, today)
    for p in conn.execute("SELECT code, name, registry_link FROM project_codes WHERE kind='project' AND domain!='P' ORDER BY code"):
        has = conn.execute("SELECT 1 FROM register_mandates WHERE code=?", (p["code"],)).fetchone() or conn.execute("SELECT 1 FROM register_initiatives WHERE code=?", (p["code"],)).fetchone()
        if not has:
            _f(findings, "register", "info", f"{p['name']} is not in the project register yet (no mandate or initiative row)", code=p["code"])
    findings.sort(key=lambda f: (SEV[f["severity"]], f["area"], f["code"] or ""))
    counts = {s: sum(1 for f in findings if f["severity"] == s) for s in SEV}
    return {"findings": findings, "counts": counts, "checked": {"hours": n_hours, "costs": n_costs, "mandates": n_mand},
            "ok": counts["error"] == 0 and counts["warning"] == 0}
