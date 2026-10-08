"""The AURORA demo: a fictitious, deliberately complicated multi-donor project, with invented funders, partners, people and mail, for demonstrations.
Run only inside the separate DEMO instance (docker-compose.demo.yml sets IG_DEMO=1 and mounts an empty data folder). It refuses to run anywhere else and refuses a database that
holds anything that is not demo data, so it can never touch the real harness. Every name, amount and address here is invented; the e-mail domain is the reserved ".example".

    python -m harness.demo_seed
"""
import hashlib
import json
import os
import sys
from datetime import date, datetime, timedelta

from harness import db, pm
from harness.config import TZ, now_local


class NotDemo(RuntimeError):
    pass


def guard(conn) -> None:
    if os.environ.get("IG_DEMO") != "1":
        raise NotDemo("This only runs inside the demo instance (IG_DEMO=1).")
    real_mail = conn.execute("SELECT COUNT(*) FROM emails WHERE from_email NOT LIKE '%.example'").fetchone()[0]
    real_projects = conn.execute("SELECT COUNT(*) FROM pm_projects WHERE demo = 0").fetchone()[0]
    if real_mail or real_projects:
        raise NotDemo("This database holds data that is not demo data. Nothing was changed.")


def _fake_hash(name: str) -> str:
    return hashlib.sha256(("aurora-demo:" + name).encode()).hexdigest()


def seed(conn, today: date | None = None) -> dict:
    guard(conn)
    today = today or now_local().date()
    if conn.execute("SELECT 1 FROM pm_projects WHERE code = 'AURORA'").fetchone():
        return {"seeded": False, "why": "AURORA is already there"}
    P = pm.add_project(conn, "AURORA", "Cyber Resilience for Small Island States", "2026-01-01", "2028-12-31", lead="Programme director (demo)", demo=True,
                       summary="A three-year programme to strengthen cyber resilience in small island states, funded by four funders in four currencies and delivered with two regional partners. Entirely fictitious.")
    F = {s: pm.add_funder(conn, n, s, role=r, currency=c, contact=ct) for s, n, r, c, ct in (
        ("HDTF", "Helvetia Digital Trust Foundation", "funder", "CHF", "Camille Roy"), ("NDA", "Nordland Development Agency", "funder", "EUR", "Ingrid Solheim"),
        ("PDFF", "Pacific Digital Futures Fund", "funder", "USD", "Tomas Aranui"), ("ACP", "Albion Cyber Philanthropies", "funder", "GBP", "Priya Ellison"),
        ("MBCC", "Mer Bleue Cyber Collective", "partner", "EUR", "Mireille Dupont"), ("KIN", "Kokua Island Network", "partner", "USD", "Leilani Kahale"))}

    def contract(short, title, amount, rate, start, end, signed, kind="grant", summary=None):
        return pm.add_contract(conn, P, F[short], title, kind=kind, amount=amount, budget_rate=rate, start_date=start, end_date=end, signed_date=signed,
                               file_path=f"Contracts/AURORA/{short}_{kind}_agreement.pdf", file_hash=_fake_hash(f"{short}{kind}"), summary=summary)
    C = {
        "HDTF": contract("HDTF", "HDTF grant agreement", 600000, None, "2026-01-01", "2028-12-31", "2025-11-20", summary="Core funding. French preferred in reports; 10% overhead cap."),
        "NDA": contract("NDA", "NDA grant agreement", 450000, 0.94, "2026-01-01", "2028-12-31", "2025-12-05", summary="Strict financial reporting every quarter; prior approval for budget moves above 10%."),
        "PDFF": contract("PDFF", "PDFF grant agreement", 380000, 0.88, "2026-01-01", "2028-12-31", "2025-12-15", summary="Results framework reporting; audit in years above the spending threshold."),
        "ACP": contract("ACP", "ACP results-based grant", 200000, 1.10, "2026-03-01", "2028-06-30", "2026-02-10", summary="Paid on acceptance of three milestones."),
        "MBCC": contract("MBCC", "Sub-grant to Mer Bleue Cyber Collective", 90000, 0.94, "2026-02-01", "2028-11-30", "2026-01-25", kind="subgrant", summary="Delivers the Indian Ocean workstream."),
        "KIN": contract("KIN", "Sub-grant to Kokua Island Network", 60000, 0.88, "2026-04-01", "2028-09-30", "2026-03-20", kind="subgrant", summary="Delivers the Pacific workstream."),
    }

    def ob(short, canon, title, **kw):
        return pm.add_obligation(conn, C[short], canon, title, **kw)
    q = dict(recurrence="quarterly", anchor="period_end")
    # HDTF
    ob("HDTF", "narrative_report", "Annual narrative report", recurrence="annual", offset_days=60, language="fr,en", format="HDTF template", detail="standard", clause="Art. 7.1")
    ob("HDTF", "financial_report", "Annual financial report (CHF)", recurrence="annual", offset_days=90, language="fr,en", format="HDTF template", detail="standard", clause="Art. 7.2")
    ob("HDTF", "visibility", "Acknowledge HDTF in all outputs", anchor="none", recurrence="none", language="fr,en", clause="Art. 9")
    ob("HDTF", "overhead", "Overhead capped at 10%", anchor="none", recurrence="none", clause="Art. 5.4")
    ob("HDTF", "notification", "Mid-term check-in summary", anchor="fixed", fixed_date=(today + timedelta(days=16)).isoformat(), recurrence="once", language="fr", detail="summary", clause="Art. 8.3")
    # NDA
    ob("NDA", "financial_report", "Quarterly financial report", offset_days=30, language="en", format="NDA workbook", detail="detailed", clause="Sect. 4.2", **q)
    ob("NDA", "narrative_report", "Annual narrative report", recurrence="annual", offset_days=45, language="en", format="NDA template", detail="detailed", clause="Sect. 4.3")
    ob("NDA", "budget_approval", "Prior written approval for reallocations above 10% of a budget line", anchor="none", recurrence="none", clause="Sect. 6.1", confirmed=False)
    ob("NDA", "overhead", "Overhead capped at 7%", anchor="none", recurrence="none", clause="Sect. 6.4")
    ob("NDA", "procurement", "Three written quotes above EUR 5,000", anchor="none", recurrence="none", clause="Sect. 6.7")
    ob("NDA", "audit", "External audit of the whole grant", anchor="end", offset_days=120, recurrence="once", language="en", format="External auditor's report", detail="line-by-line", clause="Sect. 8")
    # PDFF
    ob("PDFF", "narrative_report", "Semi-annual results report", recurrence="semiannual", anchor="period_end", offset_days=30, language="en", format="Results framework template", detail="standard", clause="Part C")
    ob("PDFF", "financial_report", "Annual financial report (USD)", recurrence="annual", offset_days=60, language="en", format="PDFF template", detail="standard", clause="Part D")
    ob("PDFF", "audit", "External audit in years with spending above USD 250,000", recurrence="annual", offset_days=120, language="en", format="External auditor's report", detail="line-by-line", clause="Part E", note="Only in years above the threshold")
    ob("PDFF", "notification", "Declaration of annual expenditure (audit threshold)", anchor="fixed", fixed_date=(today + timedelta(days=13)).isoformat(), recurrence="once", language="en", detail="summary", clause="Part E.2", confirmed=False)
    ob("PDFF", "visibility", "Acknowledge PDFF in all outputs", anchor="none", recurrence="none", language="en", clause="Part G")
    ob("PDFF", "overhead", "Overhead capped at 12%", anchor="none", recurrence="none", clause="Part B")
    # ACP
    ob("ACP", "milestone_report", "Milestone 1: baseline and threat assessment", anchor="fixed", fixed_date="2026-04-15", recurrence="once", language="en", detail="standard", clause="Sched. 1")
    ob("ACP", "milestone_report", "Milestone 2: regional playbook", anchor="fixed", fixed_date=(today + timedelta(days=14)).isoformat(), recurrence="once", language="en", detail="standard", clause="Sched. 1")
    ob("ACP", "milestone_report", "Milestone 3: final evaluation", anchor="fixed", fixed_date="2028-05-31", recurrence="once", language="en", detail="detailed", clause="Sched. 1")
    ob("ACP", "narrative_report", "Annual results summary", recurrence="annual", offset_days=30, language="en", format="Short form", detail="summary", clause="Sched. 2", confirmed=False)
    ob("ACP", "financial_report", "Annual financial summary", recurrence="annual", offset_days=90, language="en", format="Short form", detail="summary", clause="Sched. 2")
    ob("ACP", "visibility", "Acknowledge ACP with logo and caption", anchor="none", recurrence="none", language="en", clause="Sched. 3")
    # partners report to us
    ob("MBCC", "partner_report", "Quarterly activity and expense report from MBCC", offset_days=15, language="fr,en", detail="detailed", **q)
    ob("KIN", "partner_report", "Quarterly activity and expense report from KIN", offset_days=15, language="en", detail="standard", **q)
    # the no-cost extension: NDA gets until mid-2029
    amend = pm.extend_contract(conn, C["NDA"], "2029-06-30", "NDA no-cost extension 1", signed_date="2026-09-10", summary="Six more months, no extra money; moves the final report and the audit.")
    conn.execute("UPDATE pm_contracts SET file_path = 'Contracts/AURORA/NDA_amendment_1.pdf', file_hash = ? WHERE id = ?", (_fake_hash("NDAamendment1"), amend))
    conn.commit()

    def tr(short, label, exp_date, exp_amt, rec=None, rate=None, ref=None, note=None):
        kw = {}
        if rec:
            kw = dict(received_date=rec[0], received_amount=rec[1], bank_rate=rate, bank_ref=ref)
        pm.add_transfer(conn, C[short], label, expected_date=exp_date, expected_amount=exp_amt, note=note, **kw)
    tr("HDTF", "Instalment 1 (2026)", "2026-01-15", 200000, ("2026-01-16", 200000), ref="HDTF-0116")
    tr("HDTF", "Instalment 2 (2027)", "2027-01-15", 200000)
    tr("HDTF", "Instalment 3 (2028)", "2028-01-15", 200000)
    tr("NDA", "Instalment 1", "2026-02-10", 150000, ("2026-02-12", 150000), 0.9412, "NDA-0212")
    tr("NDA", "Instalment 2", "2026-08-15", 150000, ("2026-08-27", 150000), 0.9318, "NDA-0827", note="Arrived twelve days late; the rate had moved against us.")
    tr("NDA", "Instalment 3", "2027-02-15", 150000)
    tr("PDFF", "Instalment 1", "2026-03-01", 95000, ("2026-03-09", 95000), 0.8752, "PDFF-0309")
    tr("PDFF", "Instalment 2", "2026-09-01", 95000, note="Held by the fund until the first results report is accepted.")
    tr("PDFF", "Instalment 3", "2027-03-01", 95000)
    tr("PDFF", "Instalment 4", "2027-09-01", 95000)
    tr("ACP", "Milestone 1 payment", "2026-05-01", 50000, ("2026-05-04", 50000), 1.1043, "ACP-0504")
    tr("ACP", "Milestone 2 payment", "2026-12-15", 70000, note="Paid on acceptance of milestone 2.")
    tr("ACP", "Milestone 3 payment", "2028-07-15", 80000)

    # where things stand: past deadlines were met, the next ones are in hand
    rows = conn.execute("SELECT d.id, d.due_date, o.title, d.period_label FROM pm_deadlines d JOIN pm_obligations o ON o.id = d.obligation_id ORDER BY d.due_date").fetchall()
    upcoming = [r for r in rows if r["due_date"] >= today.isoformat()]
    drafting = {r["id"] for r in upcoming[:2]}
    for r in rows:
        due = date.fromisoformat(r["due_date"])
        if r["id"] in drafting:
            pm.set_deadline_status(conn, r["id"], "drafting")
        elif due < today - timedelta(days=14):
            pm.set_deadline_status(conn, r["id"], "accepted", on=(due - timedelta(days=2)).isoformat())
        elif due < today:
            pm.set_deadline_status(conn, r["id"], "submitted", on=(due - timedelta(days=1)).isoformat())
    # the fund holds instalment 2 until the first results report is accepted: that report is submitted, not accepted
    held = conn.execute("SELECT d.id FROM pm_deadlines d JOIN pm_obligations o ON o.id = d.obligation_id JOIN pm_contracts c ON c.id = o.contract_id WHERE c.funder_id = ? AND o.canon = 'narrative_report' "
                        "AND d.due_date < ? ORDER BY d.due_date DESC LIMIT 1", (F["PDFF"], today.isoformat())).fetchone()
    if held:
        pm.set_deadline_status(conn, held["id"], "submitted")
        conn.execute("UPDATE pm_deadlines SET note = 'Under review by PDFF: instalment 2 is waiting for this.' WHERE id = ?", (held["id"],))
        conn.commit()
    _everyday(conn, today)
    conn.execute("DELETE FROM deadlines WHERE source = 'pm' AND status = 'done'")          # the story's past reports were done long ago: they must not read as 'done today'
    conn.commit()
    pm.sync_core(conn, today)
    return {"seeded": True}


def _everyday(conn, today: date) -> None:
    """A little of the rest of the harness, all invented, so Today, the Inbox and the calendar are alive."""
    def at(days: int, hh: int = 9, mm: int = 0) -> datetime:
        d = today + timedelta(days=days)
        return datetime(d.year, d.month, d.day, hh, mm, tzinfo=TZ)
    conn.execute("INSERT OR REPLACE INTO draft_settings (key, value, source) VALUES ('my_address', 'director@aurora-demo.example', 'learned')")
    for slug, name, org, role, email in (("ingrid-solheim", "Ingrid Solheim", "Nordland Development Agency", "Programme officer", "ingrid@nda-demo.example"),
                                         ("tomas-aranui", "Tomas Aranui", "Pacific Digital Futures Fund", "Grants manager", "tomas@pdff-demo.example"),
                                         ("mireille-dupont", "Mireille Dupont", "Mer Bleue Cyber Collective", "Coordinator", "mireille@mbcc-demo.example"),
                                         ("camille-roy", "Camille Roy", "Helvetia Digital Trust Foundation", "Programme lead", "camille@hdtf-demo.example")):
        conn.execute("INSERT OR IGNORE INTO people (slug, name, org, role, email, space) VALUES (?,?,?,?,?, 'work')", (slug, name, org, role, email))
    conn.execute("INSERT OR IGNORE INTO project_codes (code, name, domain, kind) VALUES ('AURORA', 'Cyber Resilience for Small Island States', 'W', 'project')")
    for title, due, code in (("Collect Q3 expense statements from Mer Bleue and Kokua", today + timedelta(days=2), "AURORA"),
                             ("Prepare the evidence pack for ACP milestone 2", today + timedelta(days=9), "AURORA"),
                             ("Ask NDA to approve moving 12% from travel to training", today + timedelta(days=5), "AURORA"),
                             ("Reconcile the NDA instalment 2 exchange loss in the budget", today - timedelta(days=3), "AURORA")):
        conn.execute("INSERT OR IGNORE INTO tasks (title, due_date, project_code, source, source_ref, sensitivity) VALUES (?,?,?,'demo',?, 'S1')", (title, due.isoformat(), code, title))
    conn.execute("INSERT OR IGNORE INTO waiting_on (description, person, since_date, source, source_ref) VALUES ('PDFF to release instalment 2 once the first results report is accepted', 'tomas-aranui', ?, 'demo', 'w1')",
                 ((today - timedelta(days=20)).isoformat(),))
    for title, start, end, loc in (("AURORA steering call (HDTF, NDA, PDFF, ACP)", at(3, 14), at(3, 15, 30), "Video call"), ("Workshop: Pacific regional playbook", at(6, 9), at(6, 12), "Online"),
                                   ("Quarter-end close with the finance officer", at(7, 10), at(7, 11), "Office")):
        conn.execute("INSERT OR IGNORE INTO calendar_events (title, start, end, all_day, status, space, location, source, source_ref) VALUES (?,?,?,0,'confirmed','work',?,'demo',?)",
                     (title, start.isoformat(), end.isoformat(), loc, title))
    mails = (
        ("m1", "Ingrid Solheim", "ingrid@nda-demo.example", "Q3 financial report: updated workbook (v4)", 6, "Please use the updated NDA workbook (v4) for the Q3 report. The deadline is unchanged, 30 October. Can you confirm you received it?",
         "needs confirmation of the new template", "confirm receipt", (today + timedelta(days=16)).isoformat(), 3, 11.5, "ingrid-solheim", 1),
        ("m2", "Tomas Aranui", "tomas@pdff-demo.example", "Instalment 2 and the first results report", 20, "Our review of the first results report is complete. We will release instalment 2 as soon as you clarify how indicator 3.2 was measured. Thank you.",
         "asks how an indicator was measured", "reply with clarification", None, 3, 12.0, "tomas-aranui", 1),
        ("m3", "Mireille Dupont", "mireille@mbcc-demo.example", "Our Q3 report will arrive two days late", 30, "Apologies: our accountant is away, so the Q3 report will reach you on 17 October instead of 15 October.",
         "partner report will be late", "acknowledge", None, 2, 9.0, "mireille-dupont", 1),
        ("m4", "Camille Roy", "camille@hdtf-demo.example", "Invitation: HDTF partners' day, 12 November", 52, "We would be delighted if you could join our annual partners' day in Zurich on 12 November, and say a few words about AURORA.",
         "invitation to speak", "reply to invitation", (today + timedelta(days=30)).isoformat(), 1, 8.0, "camille-roy", 1),
    )
    for tid, name, addr, subj, hours_ago, body, why, action, deadline, urgency, score, slug, direct in mails:
        rec = datetime.fromtimestamp(datetime.now(TZ).timestamp() - hours_ago * 3600, TZ).isoformat(timespec="seconds")
        conn.execute("INSERT OR IGNORE INTO emails (thread_id, message_id, from_name, from_email, subject, received_at, snippet, body, direct, triage_status, needs_reply, why, action, deadline, urgency, score, "
                     "to_addrs, cc_addrs, history, person_slug) VALUES (?,?,?,?,?,?,?,?,?,'done',1,?,?,?,?,?,?,?,?,?)",
                     (f"demo-{tid}", f"demo-{tid}@aurora-demo.example", name, addr, subj, rec, body[:120], body, direct, why, action, deadline, urgency, score,
                      json.dumps(["director@aurora-demo.example"]), json.dumps([]), json.dumps([]), slug))
    conn.commit()


def main() -> None:
    conn = db.connect()
    db.migrate(conn)
    try:
        r = seed(conn)
    except NotDemo as e:
        sys.exit(f"Refused: {e}")
    print("AURORA demo data created." if r["seeded"] else f"Nothing changed: {r['why']}.")


if __name__ == "__main__":
    main()
