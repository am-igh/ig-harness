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

from harness import db, demo_contracts, pm, pm_reports
from harness.config import DATA_DIR
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


def _write_contract(name: str, data: bytes) -> None:
    folder = DATA_DIR / "contracts"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / name).write_bytes(data)


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
        pdf = demo_contracts.render(short, {"signed": signed, "amount": amount, "currency": conn.execute("SELECT currency FROM pm_funders WHERE id = ?", (F[short],)).fetchone()[0], "rate": rate, "start": start, "end": end})
        name = f"{short}_{kind}_agreement.pdf"
        _write_contract(name, pdf)
        return pm.add_contract(conn, P, F[short], title, kind=kind, amount=amount, budget_rate=rate, start_date=start, end_date=end, signed_date=signed,
                               file_path=f"Contracts/AURORA/{name}", file_hash=hashlib.sha256(pdf).hexdigest(), summary=summary)
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
    pdf = demo_contracts.render("NDA_AMEND", {"signed": "2026-09-10", "end": "2029-06-30", "old_end": "2028-12-31"})
    _write_contract("NDA_amendment_1.pdf", pdf)
    conn.execute("UPDATE pm_contracts SET file_path = 'Contracts/AURORA/NDA_amendment_1.pdf', file_hash = ? WHERE id = ?", (hashlib.sha256(pdf).hexdigest(), amend))
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
    _workspace_story(conn, today)
    conn.execute("DELETE FROM deadlines WHERE source = 'pm' AND status = 'done'")          # the story's past reports were done long ago: they must not read as 'done today'
    conn.commit()
    pm.sync_core(conn, today)
    return {"seeded": True}


def _deadline_id(conn, funder: str, title_like: str, nth: int = 0) -> int | None:
    rows = conn.execute("SELECT d.id FROM pm_deadlines d JOIN pm_obligations o ON o.id = d.obligation_id JOIN pm_contracts c ON c.id = o.contract_id JOIN pm_funders f ON f.id = c.funder_id "
                        "WHERE f.short = ? AND o.title LIKE ? ORDER BY d.due_date", (funder, title_like)).fetchall()
    return rows[nth]["id"] if len(rows) > nth else None


def _workspace_story(conn, today: date) -> None:
    """Documents behind a few reporting deadlines: a funder's form, templates, drafts with versions and a submitted copy (references only point at invented paths)."""
    q3 = next((r["id"] for r in conn.execute("SELECT d.id FROM pm_deadlines d JOIN pm_obligations o ON o.id = d.obligation_id JOIN pm_contracts c ON c.id = o.contract_id JOIN pm_funders f ON f.id = c.funder_id "
                                              "WHERE f.short = 'NDA' AND o.canon = 'financial_report' AND d.due_date >= ? ORDER BY d.due_date LIMIT 1", (today.isoformat(),))), None)
    if q3:
        pm_reports.attach_reference(conn, q3, "funder_form", "NDA financial workbook v4", "Funder forms/NDA/NDA_financial_workbook_v4.xlsx", "Use v4, not v3 (see Ingrid's email)")
        pm_reports.make_template(conn, q3)
        d = pm_reports.start_draft(conn, q3)
        pm_reports.save_version(conn, d["id"], d["content"] + "\n\n## Working notes\n\n- Instalment 2 arrived twelve days late at 0.9318: explain the exchange loss under the variances.\n- Waiting for Mer Bleue's Q3 numbers (promised for 17 October).\n- 12% travel-to-training move still needs NDA's written approval.\n")
    ms = next((r["id"] for r in conn.execute("SELECT d.id FROM pm_deadlines d JOIN pm_obligations o ON o.id = d.obligation_id JOIN pm_contracts c ON c.id = o.contract_id JOIN pm_funders f ON f.id = c.funder_id "
                                              "WHERE f.short = 'ACP' AND o.title LIKE 'Milestone 2%' LIMIT 1")), None)
    if ms:
        pm_reports.make_template(conn, ms)
        d = pm_reports.start_draft(conn, ms)
        pm_reports.save_version(conn, d["id"], d["content"].replace("- [ ] The deliverable itself", "- [x] The deliverable itself (playbook v1.2, final)").replace("- [ ] A short note on what changed", "- [ ] A short note on what changed (Samoa pilot: draft in progress)"))
        pm_reports.attach_reference(conn, ms, "funder_form", "ACP milestone acceptance form", "Funder forms/ACP/ACP_milestone_acceptance_form.docx", "Signed by the director before sending")
    held = conn.execute("SELECT d.id FROM pm_deadlines d JOIN pm_obligations o ON o.id = d.obligation_id JOIN pm_contracts c ON c.id = o.contract_id JOIN pm_funders f ON f.id = c.funder_id "
                        "WHERE f.short = 'PDFF' AND o.canon = 'narrative_report' AND d.status = 'submitted' ORDER BY d.due_date DESC LIMIT 1").fetchone()
    if held:
        pm_reports.attach_reference(conn, held["id"], "submitted", "PDFF semi-annual results report, as submitted", "Submitted/PDFF/PDFF_results_report_H1_2026.pdf", "Under review: instalment 2 waits for the answer on indicator 3.2")
    chk = next((r["id"] for r in conn.execute("SELECT d.id FROM pm_deadlines d JOIN pm_obligations o ON o.id = d.obligation_id JOIN pm_contracts c ON c.id = o.contract_id JOIN pm_funders f ON f.id = c.funder_id "
                                               "WHERE f.short = 'HDTF' AND o.title LIKE 'Mid-term%' LIMIT 1")), None)
    if chk:
        pm_reports.make_template(conn, chk)


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
    people = (("priya-ellison", "Priya Ellison", "Albion Cyber Philanthropies", "Programme director", "priya@acp-demo.example"),
              ("leilani-kahale", "Leilani Kahale", "Kokua Island Network", "Director", "leilani@kin-demo.example"),
              ("daniel-moreau", "Daniel Moreau", "ICT4Peace (demo finance)", "Finance officer", "daniel@aurora-demo.example"),
              ("marguerite-faure", "Marguerite Faure", "Faure & Partners (auditors)", "Audit partner", "marguerite@faure-demo.example"))
    for slug, name, org, role, email in people:
        conn.execute("INSERT OR IGNORE INTO people (slug, name, org, role, email, space) VALUES (?,?,?,?,?, 'work')", (slug, name, org, role, email))
    conn.execute("INSERT OR IGNORE INTO waiting_on (description, person, since_date, source, source_ref) VALUES (?, 'camille-roy', ?, 'demo', 'w2')",
                 ("Lakeside Cyber Dialogue to confirm Hana Petrov or Joao Marques as the AURORA panel moderator, and whether the session is in person or online", (today - timedelta(days=9)).isoformat()))
    me = "director@aurora-demo.example"
    earlier_me = [{"from_me": True, "from_email": me, "from_name": "Me", "body": "Thank you, we would be glad to take part. Could you tell us the format and who will moderate?"}]
    # (id, name, address, subject, hours ago, body, why, action, deadline, urgency, score, person slug, needs reply, status, extras)
    mails = (
        ("m1", "Ingrid Solheim", "ingrid@nda-demo.example", "Q3 financial report: updated workbook (v4)", 6,
         "Dear Anne-Marie, please use the updated NDA workbook (v4) for the Q3 financial report; the v3 file we sent in July has an error in the overhead sheet that would make your 7% cap look breached when it is not. The deadline is unchanged: 30 October. Could you confirm you received v4? Many thanks, Ingrid",
         "needs confirmation of the new template", "confirm receipt", (today + timedelta(days=16)).isoformat(), 3, 12.5, "ingrid-solheim", 1, "done", {}),
        ("m2", "Tomas Aranui", "tomas@pdff-demo.example", "Instalment 2 and the first results report", 20,
         "Anne-Marie, our review of the first results report is complete and the committee was positive. We will release instalment 2 as soon as you clarify how indicator 3.2 (number of officials trained) was measured: the report counts attendance, while the framework says completion of the full course. A short note is enough. Best, Tomas",
         "asks how an indicator was measured", "reply with clarification", None, 3, 12.0, "tomas-aranui", 1, "done", {}),
        ("m3", "Mireille Dupont", "mireille@mbcc-demo.example", "Our Q3 report will arrive two days late", 30,
         "Bonjour Anne-Marie, our accountant is away this week, so the Q3 report for Mer Bleue will reach you on 17 October instead of 15 October. All activity data are ready; only the expense reconciliation is waiting. Apologies for the inconvenience. Mireille",
         "partner report will be late", "acknowledge", None, 2, 9.0, "mireille-dupont", 1, "done", {}),
        ("m4", "Camille Roy", "camille@hdtf-demo.example", "Invitation : journée des partenaires de la HDTF, 12 novembre", 52,
         "Chère Madame Buzatu, nous serions très heureux de vous accueillir à notre journée annuelle des partenaires, le 12 novembre à Zurich, et que vous présentiez AURORA en dix minutes. Merci de nous indiquer votre réponse avant le 30 octobre. Avec nos meilleures salutations, Camille Roy",
         "invitation to speak (in French)", "reply to invitation", (today + timedelta(days=22)).isoformat(), 1, 8.5, "camille-roy", 1, "done", {}),
        ("m5", "Hana Petrov", "hana.petrov@lakeside-demo.example", "Re: AURORA panel at the Lakeside Cyber Dialogue", 4,
         "Dear Anne-Marie, thank you for your patience. We are still finalising the line-up and will come back to you very soon with the format. Warm regards, Hana Petrov, programme committee",
         "no question asked", None, None, 1, 3.0, None, 0, "done", {"history": earlier_me, "cc": ["camille@hdtf-demo.example"]}),
        ("m6", "Priya Ellison", "priya@acp-demo.example", "Milestone 2: the evidence we need to see", 14,
         "Anne-Marie, to accept milestone 2 (regional playbook) our board needs three things: the playbook itself, evidence that at least four island governments adopted it, and a one-page note on what changed after the pilot in Samoa. Please send them by 22 October so we can release the second payment of GBP 70,000 on schedule. Priya",
         "three items needed by 22 October", "prepare evidence pack", (today + timedelta(days=14)).isoformat(), 3, 13.0, "priya-ellison", 1, "done", {"history": earlier_me}),
        ("m7", "Leilani Kahale", "leilani@kin-demo.example", "Bank fees on our USD sub-grant payment", 26,
         "Hello Anne-Marie, the USD 15,000 you sent us arrived as USD 14,790: our bank deducted USD 210 in fees, and we now cannot pay the Tonga training venue in full. Can AURORA cover the difference, and if so under which budget line? I attach the bank advice. Aloha, Leilani",
         "asks AURORA to cover bank fees", "decide and reply", None, 2, 10.0, "leilani-kahale", 1, "done", {}),
        ("m8", "Daniel Moreau", "daniel@aurora-demo.example", "NDA reallocation: needs your signature before Friday", 8,
         "Anne-Marie, moving EUR 18,000 from travel to training is 12% of the travel line, which is above NDA's 10% limit, so we need their written approval before we commit the money. I have drafted the request: it needs your signature and the revised budget table. I can send it to Ingrid as soon as you sign. Daniel",
         "needs your signature", "sign the request", (today + timedelta(days=2)).isoformat(), 3, 12.8, "daniel-moreau", 1, "done", {}),
        ("m9", "Sofia Lindqvist", "sofia@nordic-tech-demo.example", "Comment for an article on cyber resilience in island states", 10,
         "Dear Ms Buzatu, I am writing a piece for Nordic Tech Review about why small island states are targeted by ransomware. Would you give me a short comment on what AURORA has learned so far? My deadline is Friday at noon, and a ten-minute call would also work. Best wishes, Sofia Lindqvist",
         "press request, Friday deadline", "reply or decline", (today + timedelta(days=3)).isoformat(), 2, 9.5, None, 1, "done", {}),
        ("m10", "Marguerite Faure", "marguerite@faure-demo.example", "Audit scope for AURORA: does 2026 spending exceed USD 250,000?", 40,
         "Dear Anne-Marie, to scope the external audit I need to know whether PDFF-funded spending in 2026 will exceed the USD 250,000 threshold in Part E of the grant. If it does, the audit is mandatory and due four months after year end; if not, we can plan a lighter review. Please send the year-to-date PDFF expenditure when you can. Kind regards, Marguerite",
         "asks for year-to-date PDFF spending", "send expenditure figure", None, 2, 9.0, "marguerite-faure", 1, "done", {}),
        ("m11", "Ingrid Solheim", "ingrid@nda-demo.example", "FYI: signed copy of amendment no. 1", 90,
         "For your records: the fully signed copy of amendment no. 1 (no-cost extension to 30 June 2029) is attached. No action needed on your side. Ingrid",
         "information only", None, None, 1, 0.0, "ingrid-solheim", 0, "done", {}),
        ("m12", "Digital Trust Weekly", "news@digitaltrust-demo.example", "This week in digital trust: ten stories you may have missed", 12,
         "Your weekly briefing on digital trust, privacy and cyber policy. Unsubscribe at any time.", "newsletter", None, None, 1, 0.0, None, 0, "skipped", {"bulk": 1}),
        ("m13", "IT Support", "it-support@mail-secure-login.example", "URGENT: verify your Workspace password within 24 hours", 5,
         "Your mailbox will be suspended unless you verify your password at the link below.", "looks like phishing", None, None, 1, 0.0, None, 0, "skipped", {"bulk": 1}),
        ("m14", "Camille Roy", "camille@hdtf-demo.example", "Re: AURORA annual narrative report: French summary", 70,
         "Merci pour votre message. Nous attendons avec plaisir votre rapport annuel.", "you replied last", None, None, 1, 0.0, "camille-roy", 0, "skipped", {"last_from_me": 1}),
    )
    for tid, name, addr, subj, hours_ago, body, why, action, deadline, urgency, score, slug, needs, status, extra in mails:
        rec = datetime.fromtimestamp(datetime.now(TZ).timestamp() - hours_ago * 3600, TZ).isoformat(timespec="seconds")
        conn.execute("INSERT OR IGNORE INTO emails (thread_id, message_id, from_name, from_email, subject, received_at, snippet, body, direct, bulk, last_from_me, triage_status, needs_reply, why, action, deadline, "
                     "urgency, score, to_addrs, cc_addrs, history, person_slug) VALUES (?,?,?,?,?,?,?,?,1,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                     (f"demo-{tid}", f"demo-{tid}@aurora-demo.example", name, addr, subj, rec, body[:140], body, extra.get("bulk", 0), extra.get("last_from_me", 0), status, needs, why, action, deadline, urgency, score,
                      json.dumps([me]), json.dumps(extra.get("cc", [])), json.dumps(extra.get("history", [])), slug))
    # invented events (some confirmed, so the horizon of "Geneva and beyond" shows what confirmed looks like); real public listings are added by `make demo-events`
    for key, title, start, end, venue, city, geneva, status, role, topics, online in (
            ("lakeside", "Lakeside Cyber Dialogue", today + timedelta(days=9), today + timedelta(days=10), "Lakeside Convention Centre", "Geneva", 1, "tentative", "panelist", "cyber,peace", 0),
            ("hdtf", "HDTF Partners' Day", date(2026, 11, 12), date(2026, 11, 12), "Zurich", "Zurich", 0, "invited", "speaker", "tech for good", 0),
            ("playbook", "AURORA regional playbook workshop", today + timedelta(days=6), today + timedelta(days=6), "Online", None, 0, "confirmed", "facilitator", "cyber,tech for good", 1),
            ("islands", "Island States Cyber Resilience Forum", today + timedelta(days=30), today + timedelta(days=32), "Convention hall", "Port Vila", 0, "confirmed", "speaker", "cyber", 0),
            ("roundtable", "Digital Trust Roundtable", today + timedelta(days=21), today + timedelta(days=21), "Brussels", "Brussels", 0, "none", None, "tech for good", 0)):
        conn.execute("INSERT OR IGNORE INTO events (dedupe_key, title, start, end, all_day, venue, city, online, geneva, role, derived_status, source_kind, tier, topics, relevant) VALUES (?,?,?,?,1,?,?,?,?,?,?,'demo','S0',?,1)",
                     (f"demo:{key}", title, start.isoformat(), (end + timedelta(days=1)).isoformat() if end != start else None, venue, city, online, geneva, role, status, topics))
    conn.commit()


def import_listings(conn) -> dict:
    """Read the public event listings the demo fetched for itself (tools/events_helper.py pull, into the demo data folder) and turn the demo calendar into events. Nothing else is imported."""
    from harness import events as E
    from harness.config import DATA_DIR
    from harness.importers.public_events import import_public_events
    guard(conn)
    r = import_public_events(conn, DATA_DIR)
    E.sync_calendar(conn)
    return {"added": sum(x.added for x in r), "updated": sum(x.updated for x in r), "notes": [n for x in r for n in x.notes]}


def main() -> None:
    conn = db.connect()
    db.migrate(conn)
    if "--events" in sys.argv:
        try:
            print(import_listings(conn))
        except NotDemo as e:
            sys.exit(f"Refused: {e}")
        return
    try:
        r = seed(conn)
    except NotDemo as e:
        sys.exit(f"Refused: {e}")
    print("AURORA demo data created." if r["seeded"] else f"Nothing changed: {r['why']}.")


if __name__ == "__main__":
    main()
