# Demo scripts: the AURORA scenario

Two versions of the same story, for the demo instance (<http://localhost:5174>, purple DEMO banner, all data fictitious): a **2-minute live scenario** (for a 5-minute slot) and a **15-minute walkthrough**. Spoken lines are suggestions in your own voice; click paths match the demo as it stands on 13 Oct 2026.

## The scenario in one paragraph

AURORA is a three-year programme that helps small island states become more resilient to cyberattacks. It is run by a small organisation and paid for by **four funders in four currencies**: a Swiss foundation (CHF 600,000, reports in French), a Nordic agency (EUR 450,000, quarterly financial reports and strict budget rules), a Pacific fund (USD 380,000, instalments released only when the previous results report is accepted) and a London philanthropy (GBP 200,000, paid when milestones are accepted). Two regional partners deliver part of the work under sub-grants. Every funder has its own deadlines, templates, languages and rules, and the money arrives at different bank rates. The director needs one place that shows what is pressing, and keeps it all on her own computer.

Everything in the demo is invented: funders, partners, people, amounts, contracts and emails.

## Before either demo (10 minutes, ideally the day before and again an hour before)

1. Open the **Docker** app and wait until it says it is running.
2. In Terminal, in the ig-harness folder: `make demo-reset`. It restarts the demo with fresh dates and fetches the current public event listings (about two minutes).
3. Open <http://localhost:5174>. The purple **DEMO** banner must be visible. Close every tab of the real harness (port 5173) so it cannot appear on screen.
4. **Warm up the model** with one question in the chat box, for example "What is overdue?" (about a minute). Do this before you go on stage; the first answer after a long idle is the slowest.
5. Check the title of the first red item on Today ("PDFF: first results report correction…") and that **Contracts & funders** opens the AURORA card.
6. Not in the demo: Research the web, Gmail drafts, scans. Do not click them.
7. If something goes wrong on stage: reload the page; if that fails, say "the screen needs a moment" and carry on with the next beat, which does not depend on the one before.

---

# Version 1: the 2-minute scenario (tonight)

Use it inside your 5-minute slot as:

| Time | What |
|---|---|
| 0:00 to 0:45 | Who you are and the problem (your own words; one sentence of the paragraph above) |
| 0:45 to 2:45 | **The 2-minute scenario below, live** |
| 2:45 to 4:00 | Why it is built this way: everything stays on this computer, local AI, a person confirms every step, it never sends email |
| 4:00 to 5:00 | Questions, or what you would like from the audience |

## The 2 minutes, beat by beat

**Beat 1, "Monday morning" (0:00 to 0:35). Stay on Today.**
> "This is the morning view for a small organisation with four funders. Everything here is invented. Red is the single most important overdue item: a correction to a report one funder is waiting on. Orange and yellow are what comes next. I did not colour these by hand: it scores them, a local AI model ranks them, and if I disagree I flag one, and it learns from me."

Click: point at the red item and its label "Top priority"; click the **⚑** on it and show "Why it is where it is" (reasons); close the menu.

**Beat 2, "Four funders, four currencies" (0:35 to 1:15). Click Contracts & funders, then the AURORA card.**
> "AURORA has four funders in four currencies. At the top: what we budgeted, what has arrived, and the exchange effect: the bank's rate on the day the money arrived against the rate in the budget. Here one instalment is late and the page says why: that funder holds it until the first results report is accepted. And five reports fall due within the same fortnight: this warns me before it happens."

Click: point at the strip, then the two yellow alerts (busy fortnight, late instalment).

**Beat 3, "The contract and the report" (1:15 to 1:45). Scroll to Funders and contracts.**
> "Each contract opens right here. This is the Nordic agency's contract, a fictitious one."

Click: the PDF name in the NDA row (pop-out opens). Point at the clause list on the right ("what this contract requires"). Close it. Scroll to the **Reporting calendar**, click a report ("Quarterly financial report"). 
> "And each report knows what the funder requires, keeps their form, and builds a template from their rules and my own records. I write my draft from it, and every save is a new version."

**Beat 4, close (1:45 to 2:00). Back on the page.**
> "All of this runs on this laptop, with a local AI model. Nothing leaves it, and it never sends an email: it prepares, and I decide."

Do not start a model question during these two minutes (the answer takes about a minute).

---

# Version 2: the 15-minute walkthrough (the GPF)

Structure: the story, then seven short scenes, then what it means. About two minutes each. Adjust the depth to the room; the scenes are independent, so you can drop any of them.

## Opening (2 minutes)

> "Imagine running a small organisation that has four funders. Each one speaks a different language, pays in a different currency, wants different reports on different days, and has different rules about how you spend. The knowledge sits in contracts, spreadsheets, emails and your head. I built a control center for that, as a local application on my own computer. What you will see is a fictitious programme, AURORA, so nothing here is real. I will show how it keeps a person in charge."

Show: the banner (fictitious), then Today.

## Scene 1: Monday morning (Today), 2 minutes

- **Colours:** red for the most important overdue item, orange and yellow next, each with a label. Open **⚑** on one item: the reasons ("major deadline", "overdue 4 days", "the model ranks it #2: …"), then the choices (top priority, high, medium, normal).
- **Say:** "It learns from my choices: if I keep raising items from one project, it adjusts. And my choice always wins."
- **Tick an AURORA to-do** (for example "Collect Q3 expense statements…"). The time box appears: enter 1.5 hours for today and **Log hours**. "The hours go into my journal and then into the hours record, citing that journal row as evidence, which my audit needs."
- **Mention:** the lake at the top is the next weeks' deadlines; the jet rises with each thing done.

## Scene 2: the inbox (Inbox, or Today's email panel), 2 minutes

- Click an email (for example the funder asking how an indicator was measured): the **summary** box appears (the local model, about 40 seconds the first time).
- Point at **Replies on open items**: "A message that asks nothing, but answers something I was waiting for, would normally be missed. It is matched to what I am waiting on."
- **Say:** "It also writes draft replies, in the language and tone I use with that person, but only when I ask, and it can only create a draft."

## Scene 3: the project and its funders (Contracts & funders), 2 minutes

- Open AURORA. The strip, the **busy fortnight** alert, the **late instalment** alert with its reason.
- **Funders and contracts:** four contracts, two sub-grants (money going out), and the **amendment** (a no-cost extension that moved the end date). Click a contract name: the PDF opens in a side pop-out, with a download button.
- **Say:** "The contracts stay in my own folders. The system only knows where each one is, and keeps a fingerprint so I know it has not changed."

## Scene 4: the money (Funding transfers), 2 minutes

- Show the table: expected and arrival dates, the bank's rate, the CHF actually credited, and the gain or loss against the budget rate. Point at the Nordic instalment that arrived late and lost money to the exchange rate.
- Click **Arrived** on the late Pacific instalment and enter what the bank credited (or the bank's rate): the other figure is worked out, the alert disappears and the totals change. "The rate that counts is the one the bank assigned when the money arrived."

## Scene 5: from deadline to draft (Reporting calendar), 2 minutes

- Click **Quarterly financial report** (Nordic agency): the drawer shows the clause, the timing, the language and format, the rules of that contract (7% overhead cap, approval for budget moves above 10%), the funder's own form (kept in my folders), and a **template made from the requirement and my records for the period**.
- Open the working draft: edit, **Save as a new version**, show that version 1 is still there. "Nothing is overwritten, and a person writes the report."
- Mark the report **Submitted** and show it leave the Today lake.

## Scene 6: one piece of work, several funders (What each funder asks for), 2 minutes

- The requirement types side by side. Open **Narrative report**: four funders, four deadlines, languages and levels of detail, and a "combined plan".
- Use **Translate**: "what I already do for the Nordic agency covers for the Swiss foundation": one covered, two to adapt (language, template), two still to produce. "This is where multi-donor projects burn time."
- Click **Confirm** on a "proposed" mapping. "Proposed means a person has not yet said yes."

## Scene 7: asking it questions (the chat box), 1 to 2 minutes

- Ask: "Which funding transfers are late on AURORA, and why? And are several reports due close together?" Start it first and keep talking; the answer takes about a minute (choose the smaller Apertus model in the header picker for the Chat job to make it faster).
- **Say:** "It answers from the data on this laptop. It cannot send anything and cannot change anything." You can also type "remind me to call the auditor on Friday": it proposes a to-do and waits for your click.

## Close: what it means (1 to 2 minutes)

> "Three principles. First, it stays local: the contracts, the emails and the money are read by AI models running on this computer, not sent to a cloud. Second, a person decides: it drafts and proposes, and it cannot send an email or change a file on its own. Third, it is built around how an International Geneva organisation actually works: several funders, several currencies, several languages. If this is useful to others in Geneva, it could be packaged for them."

Possible questions and short answers:
- **"Which AI?"** Open-weight models running locally, including a Swiss one (Apertus). You choose the model for each task.
- **"Does anything leave the computer?"** Not the contracts, emails or money. The only outgoing requests are public ones: event listings, and (when I ask) web searches, which I see and can stop.
- **"Can it send emails?"** No. It can only save a draft in Gmail, after I approve that exact text.
- **"Is this real?"** The programme in this demo is invented; the application is the one I use.

## Facts to have in your head (they are in the demo)

- Budget at contract rates: CHF 1,577,400 (CHF 600,000; EUR 450,000 at 0.94; USD 380,000 at 0.88; GBP 200,000 at 1.10).
- The Nordic agency's second instalment arrived 12 days late at 0.9318 against the 0.94 budget rate: an exchange loss of about CHF 1,230 on EUR 150,000.
- The Pacific fund's second instalment (USD 95,000) is held until the first results report is accepted; the fund asked how indicator 3.2 was measured.
- Each report has its own rules: Swiss foundation, annual, French or English; Nordic agency, quarterly, English, detailed, with an external audit at the end; Pacific fund, semi-annual results report and an audit in years above USD 250,000; London philanthropy, three milestones.
- The Nordic agency's no-cost extension moves the end date from 31 Dec 2028 to 30 Jun 2029.
