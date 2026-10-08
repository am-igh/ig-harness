# The AURORA demo (for the Geneva Cyber Forum)

AURORA is a **fictitious** programme: "Cyber Resilience for Small Island States", three years, four funders in four currencies (Swiss francs, euros, US dollars, pounds), two regional partners, a no-cost extension, a late transfer, and several reports due in the same fortnight. Every funder, partner, person, amount and e-mail address is invented (e-mail addresses end in `.example`).

## Safety: it cannot show real data

The demo is a **separate copy of the harness** (project name `igdemo`, screen at <http://localhost:5174>) with its **own empty data folder** `~/IG-Harness-Demo-data`. It has none of your real folders mounted, no Gmail, no calendar, no scan folder and no register. A purple banner across the top says **DEMO**. The seeding program refuses to run anywhere except the demo and refuses a database that holds anything that is not demo data (`tests/test_demo_seed.py` proves both, and that the demo's configuration never mentions your real data folder). Your real harness at <http://localhost:5173> is untouched.

## Commands (Terminal, in the ig-harness folder)

| Command | What it does |
|---|---|
| `make demo-up` | Starts the demo and creates the AURORA data (about a minute the first time) |
| `make demo-reset` | Throws the demo's data away and rebuilds the story. **Do this before each showing**: the dates in the story are relative to the day |
| `make demo-down` | Stops the demo |

The real harness and the demo can run at the same time. Do the demo from the browser on port **5174** only, and close other tabs of the real harness before presenting.

## A run of show (about 8 minutes)

1. **Start on Today.** The DEMO banner, the lake with the reporting deadlines on the water (they come from the contracts), the invented emails, and the chat box.
2. **Open "Contracts & funders".** One project card: AURORA, four funder chips, money received against the budget, one late transfer, two busy stretches.
3. **Open AURORA.** The strip: budget at contract rates, received so far, the exchange effect (the bank's rate against the budget rate), late transfers, reports to do. Under it the two alerts: the fortnight with five reports, and the late PDFF instalment with the reason.
4. **Funders and contracts.** Four contracts in four currencies, two sub-grants to partners (money going out), the signed copies referenced by location and fingerprint (they stay in your folders), and the NDA amendment. Click **Extension** on a grant to show how a no-cost extension adds reporting periods and moves the final report and audit (then `make demo-reset`).
5. **Reporting calendar.** All deadlines by month, each with a status you can change. Mark one "Submitted" and watch it disappear from Today's lake.
6. **Funding transfers.** Each transfer with the bank's rate, the CHF actually credited and the gain or loss against the budget rate. Click **Arrived** on the late PDFF instalment: enter the CHF the bank credited (or the bank's rate) and the other is worked out; the late alert disappears and the totals update.
7. **What each funder asks for.** The requirement types side by side. Use **Translate**: "what I already do for NDA covers for HDTF": covered, needs adapting (language, template), new work. Click **Confirm** on a "proposed" mapping.
8. **Ask the harness** (chat box): "Which funding transfers are late on AURORA, and why? And are several reports due close together?" The answer comes from the demo data, on this laptop, from a local model. Answers take about a minute with the large model: ask one question beforehand to warm the model up, or pick a smaller model for the Chat job in the header picker.
9. **Close with the principles:** contracts stay where they are; confidential material is read by local models only; nothing is sent anywhere; every proposal waits for a person's confirmation.

## What is not in the demo

Gmail, the calendar, the morning-brief draft, the scan inbox, "Research the web" and the Friday hours pass are not connected (there is nothing real behind them). The chat's "Ask the harness" works on the demo data only. The mappings marked "proposed" are placeholders for what a local model will suggest when it reads real contract text; in the demo they are fixed examples.
