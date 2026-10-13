## What this is

The IG Harness is a control center that runs on one person's computer: it reads email, calendar, contracts and money records, and uses local AI models to help prioritise, summarise and draft. This note pulls out the **responsible-use principles the harness is actually built on**, and relates each to the **human-rights principles** and the main AI and data-protection frameworks they correspond to.

How to read it: each principle says what the harness *does* (a rule in the code or a test that proves it), then the rights it relates to, then where it **falls short**. Some principles have a direct human-rights anchor (privacy, non-discrimination); others come from AI-ethics and data-protection frameworks, and the note says so rather than forcing a link. It is a design document, not a legal opinion.

**Status: draft for review, 13 October 2026.** Article numbers and titles were written from knowledge of the texts and should be checked against the originals before this is published or quoted.

# The principles at a glance

| Principle | How the harness puts it into practice | Human-rights anchor |
|---|---|---|
| **1. A person decides** | Never sends email; drafts, filings and logged hours happen only after a person clicks; the AI cannot act | Human dignity and autonomy (UDHR 1) |
| **2. Privacy and confidentiality** | Four sensitivity tiers; confidential and restricted data only reach local models; personal items always restricted | Privacy and correspondence (UDHR 12, ICCPR 17) |
| **3. Minimisation and proportionality** | Read-only, narrowly scoped connections; the AI sees only what a task needs; answers are not stored | Privacy: necessity and proportionality (ICCPR 17) |
| **4. Security and safety** | No internet for the containers; one exit door for AI; allow-lists; verified backups; automated safety tests | Security of data as part of privacy (UDHR 12, ICCPR 17) |
| **5. Transparency and explainability** | Reasons shown for rankings; sources and model named; “proposed” versus “confirmed” | Access to information (UDHR 19), as a supporting link |
| **6. Accountability and non-destructive records** | Nothing of hers is overwritten or deleted; every save is a new version; evidence on journal and hours entries | Effective remedy needs a record (UDHR 8, ICCPR 2(3)), as a supporting link |
| **7. Fairness and non-discrimination** | The AI ranks her own work, not people; learning is limited to projects and kinds of item; reasons are visible | Equality and non-discrimination (UDHR 2 and 7, ICCPR 26) |
| **8. Respect for the people in the data** | Contact names need confirmation before any web query; personal items never reach the AI; only counts of attendees are kept | Privacy of third parties (UDHR 12, ICCPR 17) |
| **9. Enabling civil society, with independence** | Lightens donor-compliance work; runs on one laptop; open models; plain file formats | Association and expression (UDHR 19 and 20, ICCPR 19 and 22), as enabling conditions |
| **10. Honesty about limits** | AI output labelled and sources shown; refuses rather than guesses; the demo is marked fictitious | Access to reliable information (UDHR 19), as a supporting link |
| **11. Proportionate use of resources** | Small local models where they suffice; the model is chosen per task | Healthy environment (UNGA resolution 76/300) |

# The principles in detail

## 1. A person decides

**In practice.** The harness cannot send email: there is no send code, the Mac-side helper can only create a draft through a strict allow-list, and network rules block the send endpoints; an automated test proves a send attempt fails. A draft reaches Gmail only after the person clicks on that exact text. Documents are filed only after approving a preview of the new name and folder. Hours are logged only on a click. A requirement mapping stays “proposed” until confirmed. The AI answers in text and has no tools. When the person flags the priority of an item, that always wins over the harness.

**Anchors.** Human dignity and autonomy as the basis of human control over tools (UDHR 1: all human beings are born free and equal in dignity and rights and are endowed with reason and conscience). The UNESCO Recommendation on the Ethics of AI (human oversight and determination), the OECD AI Principles (human-centred values) and GDPR Article 22 and Convention 108+ Article 9(1)(a) (no decisions with significant effects based solely on automated processing). The harness makes no decisions about other people, so the last two are a benchmark rather than a legal requirement.

**Limits.** A ranking from a model can steer attention and invite over-reliance (automation bias). The mitigations are that the reasons are shown and a person can overrule, but they depend on the person using them.

## 2. Privacy and confidentiality

**In practice.** Data is classified into four tiers. Public material can go anywhere; internal material may go to local or approved providers; **confidential material (partner email, contracts, funder negotiations, bank records) and restricted material (payroll, identity numbers, health, credentials, and all personal items) only reaches AI models running on the computer.** Personal items are kept in a separate space, masked on screen until clicked, never given to a model and never written to the work journal. No real data or secret key is ever stored in the code repository. External AI providers are switched off by default and would require redaction, one-click approval, a monthly cap and a log of every call. A demonstration instance exists with only invented data, so real information cannot appear on a public screen.

**Anchors.** UDHR 12 (no arbitrary interference with privacy, family, home or correspondence); ICCPR 17 and the Human Rights Committee’s General Comment 16, which expects the gathering and holding of personal information to be regulated and limited; UN General Assembly resolution 68/167 on the right to privacy in the digital age; the UN Principles on Personal Data Protection and Privacy (2018: confidentiality and security); GDPR Articles 5(1)(f) and 25 and the Swiss Federal Act on Data Protection (privacy by design and by default).

**Limits.** The harness keeps excerpts of other people’s emails on the computer (to triage, summarise and draft). There is no written retention schedule yet. How well the data is protected also depends on how the computer itself is protected (disk encryption, password, backups).

## 3. Minimisation, purpose limitation and proportionality

**In practice.** Connections are read-only and narrowly scoped: Gmail is read-only apart from creating drafts, only the current year’s audit folder is visible, calendar entries keep a count of attendees and never their addresses. A model is given only the numbered facts a task needs, and a model asked to rank to-dos never sees personal ones. Chat answers are not stored, research answers wait in memory for an hour at most, and neither is ever written to notes or the journal. Web research never sees harness data. What leaves the computer as a search query is screened and logged.

**Anchors.** ICCPR 17 as read by the Human Rights Committee (interference must be lawful, necessary and proportionate); the UN Principles on Personal Data Protection and Privacy (purpose specification; proportionality and necessity); GDPR Article 5(1)(b) and (c); the UNESCO principle of proportionality and “do no harm”.

**Limits.** The size of the excerpt kept per email was chosen for usefulness, not by a formal necessity test. A written data-protection impact assessment would settle it.

## 4. Security and safety

**In practice.** The containers that hold the data have no internet access; a separate network holds the search engine, and the tests prove the data containers cannot reach it. Every AI call goes through one gateway. Web fetching is limited to public addresses, obeys robots.txt and saves nothing. Keys live in the system keychain. Backups are verified and a restore test exists, and an automated suite of safety tests (no sending, one exit door, masking, fail-safe) must stay green.

**Anchors.** Security is a precondition of privacy (UDHR 12, ICCPR 17). GDPR Article 32, the UN Principles (security), UNESCO (safety and security) and the OECD AI Principles (robustness, security and safety).

**Limits.** The software has not been independently audited. The Google permission that lets the harness create drafts also technically allows sending, which is why three separate layers prevent it. One known gap is documented: a hostile web address that changes its answer between the safety check and the connection is not blocked.

## 5. Transparency and explainability

**In practice.** Every priority carries its reasons and, when a model contributed, the model’s reason; the line under the list says which model ranked it and when. Research answers show numbered sources with the date each was read. Every draft, template and mapping is visibly marked as a proposal until a person confirms it. A log records every search that left the computer. Choosing a model for each task is done in the open.

**Anchors.** UNESCO (transparency and explainability), the OECD AI Principles (transparency and explainability), GDPR Article 5(1)(a). The link to UDHR 19 (the right to seek, receive and impart information) is a supporting one: people can only use AI-derived information well if they can see where it came from.

**Limits.** Local models are themselves opaque. The harness explains *why it asked* and *what it was given*, not how the model reasons internally.

## 6. Accountability and non-destructive records

**In practice.** The harness never overwrites or deletes the person’s files. New documents are created exclusively (an existing file is never replaced) and a name clash becomes a new version. Before any change to one of her own spreadsheets a backup is kept and the result is verified, with automatic reversal on failure. Every journal and hours entry cites its evidence. Report drafts keep every saved version.

**Anchors.** GDPR Article 5(2) (accountability), the UN Principles on Personal Data Protection (accountability), UNESCO (responsibility and accountability), the OECD AI Principles (accountability). The link to UDHR 8 and ICCPR 2(3) (an effective remedy) is a supporting one: a remedy depends on a record that can be reviewed.

**Limits.** The record is only as good as its use: nothing yet checks who else could alter the files on the computer.

## 7. Fairness and non-discrimination

**In practice.** The AI ranks the person’s own work items, not people. What the harness learns from her choices is limited to projects and kinds of item, not to individuals. The ranking shows its reasons and can always be overruled. Language and register follow the correspondent (for example the formal “vous” in French professional mail).

**Anchors.** UDHR 2 and 7 and ICCPR 26 (equality and non-discrimination); UNESCO (fairness and non-discrimination); the OECD AI Principles (fairness).

**Limits.** This has **not** been tested for bias. A ranking can favour what is loud, recent or overdue over what is important but quiet; the learned “writing style per person” could embed assumptions; and the local models inherit the biases of their training. The Inbox scoreboard, which compares models against the person’s own labels, is a start but not a bias evaluation.

## 8. Respect for the people in the data

**In practice.** A search query containing the name of someone in the contact list needs an explicit confirmation before it can leave the computer, and identity numbers, bank numbers and credentials are refused outright. Personal items never reach a model. Calendar entries record how many people were invited, never who. Saved research keeps the summary and links, not the text of the pages.

**Anchors.** UDHR 12 and ICCPR 17 apply to the people whose emails and details the harness holds, not only to its user. The UN Principles (fair and legitimate processing; confidentiality).

**Limits.** The people who write to the user are not individually told that their messages are processed by a local tool. This is ordinary for the recipient of a message, but it becomes a real question if the harness is ever shared with other organisations.

## 9. Enabling civil society, with independence

**In practice.** The harness is meant to lighten the load that several donors’ reporting rules place on small organisations: it keeps deadlines, contracts, money and requirements together and shows how one funder’s requirements map to another’s. It runs on one laptop, needs no subscription, uses open-weight models (including a Swiss one, Apertus) chosen per task, and keeps data in plain, portable formats (a database file, spreadsheets, PDFs in the person’s own folders), so there is no lock-in.

**Anchors.** Freedom of association and expression (UDHR 19 and 20, ICCPR 19 and 22) protect the space in which civil society operates. A tool like this does not guarantee those rights; it can reduce the administrative burden on organisations that exercise them and keep their sensitive information in their own hands. UDHR 27 (sharing in scientific advancement and its benefits) and the UN Global Digital Compact’s commitments to a human-rights-based digital space are supporting links for the use of open models.

**Limits.** It currently needs a recent Apple Silicon computer and is maintained by one person. Making it available to others would require a different governance model (see below).

## 10. Honesty about limits

**In practice.** AI output is labelled as such and tells the reader to check the sources; where the harness cannot do something it says so instead of guessing, and the AI is instructed to say when the information it was given does not answer the question, rather than fill the gap from memory. Nothing in the harness trains a model on the person’s data: what it learns is stored as simple, inspectable rules and counts on the computer. The demonstration is labelled fictitious on every screen.

**Anchors.** UNESCO (awareness and literacy); UDHR 19, in its supporting sense of access to reliable information.

## 11. Proportionate use of resources

**In practice.** Small local models are used where they are enough and larger ones only where needed; the model is chosen per task; no always-on cloud calls.

**Anchors.** UNESCO (sustainability). The right to a clean, healthy and sustainable environment, recognised by the UN Human Rights Council (resolution 48/13) and the General Assembly (resolution 76/300).

**Limits.** Energy use has not been measured. Running a large local model is not free of cost.

# Where the harness falls short, and what would close the gaps

1. **A written data-protection impact assessment** and **retention rules** for stored email excerpts, contacts and logs.
2. **Systematic evaluation of accuracy and bias** of the triage, summaries and priority ranking, beyond the scoreboard of the user’s own labels.
3. **An incident plan**: what to do if the computer is lost or a backup is exposed, and a check that disk encryption and backup protection are on.
4. **An independent security review** before anyone else uses the software.
5. **A notice policy** for correspondents’ data and a clear statement for donors and partners about how their information is handled.
6. **Governance for sharing.** If the harness is ever packaged for other International Geneva organisations: data-processing agreements, who is responsible for what, separation of each organisation’s data, access rights, support and update arrangements.
7. **Energy and cost awareness** for the models in use.

# How this can be used

- As the **basis for a short public statement** of the harness’s principles (one page, in plain language), once the citations are checked.
- As a **checklist for a conversation with donors, partners or a data-protection adviser** about what the tool does with their information.
- As a **reference for the demonstrations**, where the three most asked questions are what leaves the computer, whether it can send email, and which AI it uses.

# Main references

- Universal Declaration of Human Rights (1948), Articles 1, 2, 7, 8, 12, 19, 20, 27.
- International Covenant on Civil and Political Rights (1966), Articles 2(3), 17, 19, 22, 26; Human Rights Committee, General Comment No. 16 (1988) on Article 17.
- UN General Assembly resolution 68/167 (2013), The right to privacy in the digital age; OHCHR report A/HRC/48/31 (2021) on the right to privacy in the digital age.
- UN Principles on Personal Data Protection and Privacy (2018, UN High-Level Committee on Management).
- UNESCO Recommendation on the Ethics of Artificial Intelligence (2021).
- OECD Recommendation of the Council on Artificial Intelligence (2019, updated 2024).
- Council of Europe Convention 108+ (2018 amending protocol); Regulation (EU) 2016/679 (GDPR); Swiss Federal Act on Data Protection (revised, in force 1 September 2023).
- UN Guiding Principles on Business and Human Rights (2011), relevant to technology companies and suppliers.
- UN Global Digital Compact (2024); UN Human Rights Council resolution 48/13 and UN General Assembly resolution 76/300 (healthy environment).
- ICRC, Handbook on Data Protection in Humanitarian Action, for the humanitarian “do no harm” approach to data.
