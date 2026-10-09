"""The fictitious contracts behind the AURORA demo, as PDFs. Every party, amount, clause and signature is invented. The clause numbers match the requirements recorded in harness/demo_seed.py, so what the
funder-requirements screens show can be found in the contract text."""
from harness import minipdf

GRANTEE = "The Grantee (demo programme office), Geneva"


def _money(a, cur) -> str:
    return f"{cur} {a:,.0f}"


def _sig(funder_name, funder_role="Programme lead"):
    return [("sig", [("Director, the Grantee", "For the Grantee"), (funder_role + ", " + funder_name, "For the Funder")])]


def _head(no, title, funder, funder_where, p):
    return [("h1", title), ("kv", [("Agreement no.", no), ("Funder", f"{funder}, {funder_where}"), ("Grantee", GRANTEE), ("Programme", "AURORA: Cyber Resilience for Small Island States"),
                                     ("Signed", p["signed"]), ("Amount", _money(p["amount"], p["currency"])), ("Period", f"{p['start']} to {p['end']}")]), ("sp", 4)]


def hdtf(p):
    return _head("HDTF-2025-114", "GRANT AGREEMENT", "Helvetia Digital Trust Foundation", "Zurich", p) + [
        ("h2", "Article 1. Purpose"), ("p", "The Funder supports the Grantee's AURORA programme, which strengthens the cyber resilience of small island states through training, regional playbooks and peer exchange."),
        ("h2", "Article 3. Funding and payment"), ("p", f"The Funder grants a total of {_money(p['amount'], p['currency'])}, paid in three equal annual instalments of CHF 200,000, each due on 15 January of 2026, 2027 and 2028, to the account notified by the Grantee."),
        ("p", "The grant is denominated in Swiss francs. No exchange rate applies."),
        ("h2", "Article 5. Eligible costs"), ("p", "5.1 Costs are eligible if they are incurred during the period, are necessary for the programme and are supported by invoices or receipts."),
        ("p", "5.4 Overhead (indirect costs) may not exceed 10% of the direct eligible costs."),
        ("h2", "Article 7. Reporting"),
        ("p", "7.1 Narrative report. The Grantee submits an annual narrative report on the Funder's template, in French or English (French preferred), at the standard level of detail, within 60 days of the end of each calendar year."),
        ("p", "7.2 Financial report. The Grantee submits an annual financial report in Swiss francs on the Funder's template within 90 days of the end of each calendar year."),
        ("h2", "Article 8. Monitoring"), ("p", "8.3 Mid-term check-in. The Grantee sends a short summary in French of progress and risks ahead of the Funder's mid-term check-in meeting."),
        ("h2", "Article 9. Visibility"), ("p", "The Funder is acknowledged in all outputs and public communication about the programme, in French and English."),
        ("h2", "Article 11. Termination and law"), ("p", "Either party may end the agreement with 60 days' written notice. Unspent funds are returned. The agreement is governed by Swiss law; the courts of Zurich have jurisdiction.")] + _sig("Helvetia Digital Trust Foundation")


def nda(p):
    return _head("NDA/GRT/2025/0387", "GRANT AGREEMENT", "Nordland Development Agency", "Oslo-Nord (fictitious)", p) + [
        ("h2", "Section 1. Purpose"), ("p", "The Agency contributes to the AURORA programme as described in the approved proposal and budget annexed to this agreement."),
        ("h2", "Section 3. Funding, payment and currency"), ("p", f"The grant is EUR {p['amount']:,.0f}, paid in three instalments of EUR 150,000 (February 2026, August 2026 and February 2027). The budget uses an exchange rate of {p['rate']} CHF per 1 EUR. "
                                                           "Payments are credited to the Grantee's bank account in Swiss francs at the rate the bank applies on the day of receipt; the difference from the budget rate is reported in the financial report."),
        ("h2", "Section 4. Reporting"),
        ("p", "4.2 Financial reports. The Grantee submits a quarterly financial report on the Agency's workbook, at a detailed level, in English, within 30 days of the end of each quarter."),
        ("p", "4.3 Narrative report. An annual narrative report on the Agency's template, in English, at a detailed level, within 45 days of the end of each calendar year."),
        ("h2", "Section 6. Financial rules"),
        ("p", "6.1 Budget changes. Any reallocation above 10% of a budget line requires the Agency's prior written approval."),
        ("p", "6.4 Overhead may not exceed 7% of the direct eligible costs."),
        ("p", "6.7 Procurement. For purchases above EUR 5,000 the Grantee obtains at least three written quotes and keeps the selection note."),
        ("h2", "Section 8. Audit"), ("p", "An external audit of the whole grant is carried out by an independent auditor. The audit report, in English and in line-by-line detail, is due within 120 days of the end date of the agreement."),
        ("h2", "Section 10. Termination and law"), ("p", "Either party may terminate with 90 days' written notice. Disputes are settled under Swiss law, with the courts of Geneva competent.")] + _sig("Nordland Development Agency", "Programme officer")


def nda_amend(p):
    return [("h1", "AMENDMENT No. 1 TO GRANT AGREEMENT NDA/GRT/2025/0387"), ("kv", [("Funder", "Nordland Development Agency"), ("Grantee", GRANTEE), ("Signed", p["signed"]), ("Type", "No-cost extension (no change in the amount)")]), ("sp", 4),
            ("h2", "1. Extension"), ("p", f"Section 2.1 of the agreement is amended: the end date moves from {p['old_end']} to {p['end']}. The grant amount and the budget rate are unchanged."),
            ("h2", "2. Consequences for reporting"), ("p", "Quarterly financial reports continue until the new end date. The final narrative report and the external audit are due within the periods in the agreement, counted from the new end date."),
            ("h2", "3. Other terms"), ("p", "All other terms of the agreement remain in force. This amendment is part of the agreement.")] + _sig("Nordland Development Agency", "Programme officer")


def pdff(p):
    return _head("PDFF-GA-2025-061", "GRANT AGREEMENT", "Pacific Digital Futures Fund", "Suva (fictitious)", p) + [
        ("h2", "Part A. Grant"), ("p", f"The Fund grants USD {p['amount']:,.0f}, paid in four instalments of USD 95,000 on 1 March and 1 September of 2026 and 2027. Each instalment after the first is released once the preceding results report has been accepted. "
                                      f"The budget rate is {p['rate']} CHF per 1 USD; payments are credited in Swiss francs at the bank's rate on arrival."),
        ("h2", "Part B. Eligible costs"), ("p", "Overhead may not exceed 12% of the direct eligible costs."),
        ("h2", "Part C. Results reporting"), ("p", "The Grantee submits a semi-annual results report on the Fund's results framework template, in English, at the standard level of detail, within 30 days of the end of each six-month period."),
        ("h2", "Part D. Financial reporting"), ("p", "An annual financial report in US dollars on the Fund's template, within 60 days of the end of each calendar year."),
        ("h2", "Part E. Audit"), ("p", "In any calendar year in which expenditure under this grant exceeds USD 250,000, the accounts are audited by an independent external auditor within 120 days of year end."),
        ("p", "E.2 The Grantee declares its annual expenditure to the Fund by the end of October so that the Fund can tell whether an audit is required."),
        ("h2", "Part G. Visibility"), ("p", "The Fund is acknowledged in all outputs, in English and in the languages of the beneficiaries where practical."),
        ("h2", "Part H. Law"), ("p", "The agreement is governed by Swiss law, with the courts of Geneva competent.")] + _sig("Pacific Digital Futures Fund", "Grants manager")


def acp(p):
    return _head("ACP/RBG/2026/019", "RESULTS-BASED GRANT AGREEMENT", "Albion Cyber Philanthropies", "London (fictitious)", p) + [
        ("h2", "Schedule 1. Milestones and payments"), ("p", f"The grant is GBP {p['amount']:,.0f}, paid on acceptance of three milestones by the Funder's board. The budget rate is {p['rate']} CHF per 1 GBP; payments are credited at the bank's rate on arrival."),
        ("li", "Milestone 1: baseline and threat assessment: GBP 50,000 on acceptance (accepted)."), ("li", "Milestone 2: regional playbook adopted by at least four island governments: GBP 70,000 on acceptance."),
        ("li", "Milestone 3: final evaluation: GBP 80,000 on acceptance."),
        ("p", "For each milestone the Grantee submits the deliverable, evidence of adoption and a one-page note on what changed, using the Funder's acceptance form."),
        ("h2", "Schedule 2. Annual reporting"), ("p", "A short-form annual results summary within 30 days of year end and a short-form annual financial summary within 90 days of year end, in English."),
        ("h2", "Schedule 3. Visibility"), ("p", "The Funder is acknowledged with its logo and a standard caption on all published outputs."),
        ("h2", "General"), ("p", "No overhead above the rate in the approved budget. Governed by Swiss law; courts of Geneva.")] + _sig("Albion Cyber Philanthropies", "Programme director")


def mbcc(p):
    return [
        ("h1", "SUB-GRANT AGREEMENT"), ("kv", [("Agreement no.", "SUB/MBCC/2026/01"), ("Between", "The Grantee (demo programme office) and Mer Bleue Cyber Collective"), ("Signed", p["signed"]), ("Amount", _money(p["amount"], p["currency"])), ("Period", f"{p['start']} to {p['end']}")]),
        ("h2", "1. Purpose"), ("p", "Mer Bleue Cyber Collective delivers the Indian Ocean workstream of the AURORA programme."),
        ("h2", "2. Payment"), ("p", f"Payments in {p['currency']} in instalments agreed in the work plan. Bank fees on payments are borne by the Grantee."),
        ("h2", "3. Reporting"), ("p", "The partner sends a quarterly activity and expense report, in French or English, at a detailed level with receipts, within 15 days of the end of each quarter. The Grantee needs it to meet its own deadlines to its funders."),
        ("h2", "4. Rules"), ("p", "The partner follows the same procurement and acknowledgement rules as the Grantee's funders and keeps records for ten years.")] + _sig("Mer Bleue Cyber Collective", "Coordinator")


def kin(p):
    return [("h1", "SUB-GRANT AGREEMENT"), ("kv", [("Agreement no.", "SUB/KIN/2026/02"), ("Between", "The Grantee (demo programme office) and Kokua Island Network"), ("Signed", p["signed"]), ("Amount", _money(p["amount"], p["currency"])), ("Period", f"{p['start']} to {p['end']}")]),
            ("h2", "1. Purpose"), ("p", "Kokua Island Network delivers the Pacific workstream, including regional training."),
            ("h2", "2. Payment"), ("p", f"Payments in {p['currency']}. The Grantee asks its bank to cover transfer fees where the partner's bank deducts them, within the approved budget line."),
            ("h2", "3. Reporting"), ("p", "A quarterly activity and expense report in English at the standard level of detail within 15 days of the end of each quarter."),
            ("h2", "4. Rules"), ("p", "Same procurement and acknowledgement rules as the Grantee's funders.")] + _sig("Kokua Island Network", "Director")


BUILDERS = {"HDTF": hdtf, "NDA": nda, "NDA_AMEND": nda_amend, "PDFF": pdff, "ACP": acp, "MBCC": mbcc, "KIN": kin}


def render(key: str, params: dict) -> bytes:
    """The PDF for one demo contract. `params`: signed, amount, currency, rate, start, end (and old_end for the amendment)."""
    blocks = BUILDERS[key](params)
    title = next(v for k, v in blocks if k == "h1")
    return minipdf.build_pdf(f"{title} (demo)", blocks)
