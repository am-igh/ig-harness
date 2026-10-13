"""A FICTITIOUS grant agreement for trying contract onboarding. Every party, amount, clause and person is invented; the banner on every page says so.
Write it with:  python -m harness.sample_contract <folder>      (creates Sample_grant_agreement_FICTITIOUS.pdf)"""
import sys
from pathlib import Path

from harness import minipdf

NAME = "Sample_grant_agreement_FICTITIOUS.pdf"


def blocks() -> list[tuple]:
    return [
        ("h1", "GRANT AGREEMENT"),
        ("kv", [("Reference", "LPT/2026/088"), ("Funder", "Lakeside Peace Trust, Zurich (an invented foundation)"), ("Grantee", "Example Dialogue Foundation, Geneva (an invented organisation)"),
                ("Programme", "Harbour Light: Digital Dialogue for Peace"), ("Signed", "30 September 2026"), ("Grant", "EUR 360,000"), ("Period", "1 November 2026 to 31 October 2028")]), ("sp", 4),
        ("h2", "Article 1. Purpose"), ("p", "The Funder supports the Grantee's Harbour Light programme, which brings together civil society groups and technology companies to prepare shared, practical guidance on protecting people online during conflicts."),
        ("h2", "Article 2. Period"), ("p", "This agreement starts on 1 November 2026 and ends on 31 October 2028. Costs are eligible only if incurred in that period."),
        ("h2", "Article 3. Funding and payment"),
        ("p", "3.1 The Funder grants a total of EUR 360,000, denominated in euros."),
        ("p", "3.2 Payment is made in three instalments: (a) 40% (EUR 144,000) within 15 days of signature, due by 15 November 2026; (b) 30% (EUR 108,000) on 1 November 2027, once the first annual narrative report has been accepted; (c) 30% (EUR 108,000) on 1 August 2028, once the interim financial report for the second year has been accepted."),
        ("p", "3.3 For the Grantee's budget, amounts in euros are converted at a rate of CHF 0.93 per EUR 1. The Grantee records the rate actually credited by its bank on each arrival."),
        ("h2", "Article 4. Eligible costs"), ("p", "4.1 Costs are eligible if they are necessary for the programme, are incurred during the period, are recorded in the Grantee's accounts and are supported by invoices or receipts."),
        ("h2", "Article 5. Contacts"), ("p", "5.1 For the Funder: Ms Elena Marchetti, Programme Officer, elena.marchetti@example.org, +41 00 000 00 00."),
        ("h2", "Article 6. Reporting"),
        ("p", "6.1 Narrative report. The Grantee submits an annual narrative report on the Funder's template, in English or French, at the standard level of detail, within 60 days of the end of each year of the programme (the years end on 31 October)."),
        ("p", "6.2 Financial report. The Grantee submits a quarterly financial report in euros, in the Funder's spreadsheet format and in detail by budget line, within 30 days of the end of each quarter."),
        ("p", "6.3 Milestone report. The Grantee submits a short report on the first public guidance document by 30 June 2027."),
        ("p", "6.4 Final reports. A final narrative report and a final financial report are due within 90 days of the end of the agreement."),
        ("p", "6.5 External audit. The Grantee provides an external audit of the programme accounts, line by line, within 120 days of the end of the agreement."),
        ("h2", "Article 7. Budget rules"),
        ("p", "7.1 Overhead (indirect costs) may not exceed 8% of the direct eligible costs."),
        ("p", "7.2 Moving money between budget lines by more than 15% of a line requires the Funder's prior written approval."),
        ("p", "7.3 For any purchase above EUR 4,000 the Grantee obtains at least three written quotes."),
        ("h2", "Article 8. Ownership and data"), ("p", "8.1 The outputs belong to the Grantee, and the Funder may share them with credit to the Grantee. 8.2 Personal data collected in the programme is processed in Switzerland and is not shared with the Funder."),
        ("h2", "Article 9. Visibility"), ("p", "The Funder is acknowledged in all public outputs of the programme, in English."),
        ("h2", "Article 10. Special conditions"), ("p", "Any subcontract above EUR 20,000 requires the Funder's prior written approval."),
        ("h2", "Article 11. Termination and law"), ("p", "Either party may end this agreement with 90 days' written notice. Unspent funds are returned. The agreement is governed by Swiss law; the courts of Zurich have jurisdiction."),
        ("sig", [("Director, Example Dialogue Foundation", "For the Grantee"), ("Executive Director, Lakeside Peace Trust", "For the Funder")]),
    ]


def render() -> bytes:
    return minipdf.build_pdf("Grant agreement (sample, fictitious)", blocks())


if __name__ == "__main__":
    out = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
    out.mkdir(parents=True, exist_ok=True)
    (out / NAME).write_bytes(render())
    print(out / NAME)
