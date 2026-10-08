# Project management page: a first outline (proposal, 8 Oct 2026)

Status: **first version built on 8 Oct 2026 and demonstrated with the fictitious AURORA programme (see `DEMO_AURORA.md`);** contract reading by a local model, the register link and real data entry are still to come. Original status: idea. Anne-Marie asked for a fuller project and contract management area, to be built eventually. This outline is for review; nothing here is decided until she says so.

## What she asked for

A page (probably a fifth tab, or a big extension of Projects & finance) where she can:

1. add new projects;
2. record who the funders are;
3. store the contracts;
4. track contract requirements;
5. record funding transfers, including those in other currencies and the exchange rate used;
6. track reporting deadlines and requirements;
7. translate one funder's requirements into another's for multi-donor projects;
8. keep other relevant contract-management information.

## Principles (from the standing rules)

- Contracts, funder terms and transfers are **S2: local models only**. Nothing about them goes to a search engine or an online model.
- The model only **proposes** (for example "this clause looks like a narrative report due 30 days after the end date"); she confirms. Nothing is invented and nothing is written to her files without her click.
- Her existing files stay the source: contracts stay in her folders (the harness stores the path and a content hash, not a second copy, unless she asks otherwise). Anything written to `Registre_Projets.xlsx` goes through the existing append-only register writer.
- Deadlines created here feed the existing deadline system, so they appear on the Today lake with D-14 and D-3 warnings.

## Proposed building blocks

| Block | What it holds |
|---|---|
| **Projects and funders** | Project record (code, name, status, dates, partners, lead), funders per project with their share, contact people. Builds on the project codes and register data already mirrored. |
| **Contracts** | One entry per contract or amendment: parties, dates, amount and currency, file reference (path and hash), status. Optional local reading of the contract to suggest key terms for her to confirm. |
| **Obligations** | Each requirement from a contract: what (narrative report, financial report, audit, visibility, ethics, procurement rule, eligible costs, overhead cap), the clause, the deadline rule ("30 days after end date"), format and language, status. Each can create real deadlines. |
| **Funds and transfers** | Instalments expected and received: date, amount in the contract currency, CHF amount received, **exchange rate used and where it came from**, bank-statement line it matches, and the exchange difference. |
| **Reporting calendar** | Every report due, per funder and project, with status (not started, drafting, submitted, accepted) and the link to what was submitted. |
| **Funder crosswalk** | A common list of requirement types. Each funder's clause is mapped to it, so for a multi-donor project the page can show what one report covers for both donors, what differs (dates, format, language, financial detail) and what still needs a separate piece. The local model proposes mappings from the contract text; she confirms. |
| **Other contract management** | Amendments and no-cost extensions, eligible-cost and VAT rules, overhead rate, visibility and acknowledgement duties, audit rights, risks, close-out checklist, contact log. |

## Suggested order

1. **Read-only first:** a projects and funders view built from the register, plus a place to add a funder to a project.
2. **Contracts and obligations**, with deadlines flowing into Today.
3. **Funds and transfers with exchange rates**, matched to the bank statements already filed.
4. **The crosswalk** for multi-donor projects.
5. Everything else on the list, as it proves useful.

## Decisions so far (8 Oct 2026)

- **Contracts stay where they are** (referenced by path and hash, not copied).
- **Exchange rate that counts:** the rate the bank assigned when the money arrived (from the bank statement), not a published rate.
- **Scale today:** about 3 active projects, and no funders with reporting duties beyond those; more expected soon.
- **Demo:** a fictitious, deliberately complicated multi-donor project is wanted for next week's Geneva Cyber Forum. It must live in a separate demo data folder so no real data can appear.

## Still to settle

1. **One source of truth:** `Registre_Projets.xlsx` as master, the new page as master, or a hybrid (see the pros and cons discussed with Anne-Marie).
2. **Later sharing:** should the design keep other organisations in mind (a possible FAGI version)?
