# Phase 5 plan: Events (Geneva and beyond)

Written 2 Oct 2026 with Anne-Marie. No real data in this file (rule 8); it describes patterns found in her inbox, not its content.

## Goal
One **Events** tab (the Geneva tab, enlarged): conferences and events relevant to her work, from her inbox of the past year (especially ones she was **personally invited** to), the International Geneva listings, and the Club Diplomatique de Genève, with the ones she **confirmed highlighted**.

## What the inbox scan found (patterns, not content)
- Volumes are high: every event-type search (Club Diplomatique, Genève internationale newsletter, calendar invitations, registration services) hits the 200+ result ceiling for the year. Dedupe and filtering are essential; plenty of noise (vendor promotions).
- **Club Diplomatique**: monthly newsletters, invitations and reminders. Subject line is reliable: `Invitation | <title>, <date> at <time>[, <venue>]`; the plain-text part is a stale template, so the **subject** (and HTML) must be read, not the text part. Also a members' area and cultural offers (not events to track).
- **Genève internationale**: weekly "Upcoming events" newsletter. The plain-text part is empty; the event tables (theme, organizer, event, date, location, link) are only in the **HTML part**.
- **Personal invitations** from conference organisers, ministries, universities, think tanks (speaking requests, awards, closed-door dialogues). Signals: addressed by name, single recipient, not a bulk sender.
- **Confirmation signals**: Luma "Registration approved/confirmed"; organiser "Registration Confirmed" emails (summit, cyber week, trade shows); Google Calendar "Accepted"; direct "You're confirmed" emails; her own replies.
- **Her Google Calendar** is the best truth for "I'm going", but the current importer drops each event's RSVP status, location and link.

## Sources (and sensitivity)
| Source | How | Tier |
|---|---|---|
| Google Calendar | extend the Mac-side helper (read-only): RSVP status (accepted / tentative / needs action), location, link, organizer | S2 |
| Inbox event emails (past year, then incremental) | Gmail helper backfill with event-focused searches; rules first (Club Diplomatique subject, Luma, calendar invitations, registration confirmations); HTML parser for the Genève internationale tables; local model (job `event_extract`, S2) for free-form invitations | S2 (local only) |
| Public listings | a Mac-side `events_helper` fetches a short allow-list of public pages (geneve-int.ch calendar, clubdiplomatique.ch events, UNOG major meetings) at low frequency, respecting robots.txt; writes JSON into `~/IG-Harness-data`; containers stay offline | S0 |

## Data model
- `events`: title, start, end, all_day, venue, city, online, url, organizer, topics, geneva flag, role (attendee / speaker / panelist / judge / moderator), `my_status` (none, invited, interested, registered, confirmed, speaking, declined), dedupe key, source tier.
- `event_evidence`: every signal that supports an event (email thread, calendar response, listing URL, date, kind). `my_status` is derived from the strongest evidence (declined overrides), and she can override it in one click.
- Merge rule: same event from newsletter + invitation + calendar + registration becomes one card (normalised title + date + fuzzy match; unsure cases are asked).

## Screens
- **Events tab**: agenda grouped by week (default), filters (Confirmed, Invited, Geneva, Online, topic, date range), search; past year as an archive.
- **Confirmed events are highlighted**: strong purple edge, "You're in" badge, role chip (Speaking, Panelist...), evidence line ("registration approved 2 Oct"). Declined events are greyed. Clashes between confirmed events, or with calendar busy time, get a warning.
- **Needs a decision**: invitations with an RSVP deadline or a speaking request, newest first, with "I'm going / Not going / Interested" and "Draft a reply" (existing drafting, approval before saving to Gmail).
- **Event drawer**: details, evidence (links to the Gmail threads), people from Suivi, notes and follow-ups (existing notes feature).
- **Today**: a "Coming up" strip (confirmed events in the next 7 days, clashes); events as marks on the lake band (periwinkle).
- Existing Calendar widget gets an Events layer.

## Slices
1. **5.1** Calendar RSVP, location and link; `events` store; Events tab skeleton with confirmed highlighting from the calendar. (Quick win.)
2. **5.2** Past-year inbox backfill with deterministic rules (Club Diplomatique, Luma, calendar invitations, registration confirmations, Genève internationale HTML tables); archive view.
3. **5.3** Local-model extraction for free-form invitations; personal-invitation detection; her "this is relevant / not relevant" feedback (noise block-list, like the email labels).
4. **5.4** Public listings helper (geneve-int.ch, clubdiplomatique.ch, UNOG) and merge/dedupe.
5. **5.5** Clash detection, Today strip, Monday digest, reply drafts.
6. **5.6** Chat bar and local dictation (from the original Phase 5 scope), if still wanted.

## Progress
- 5.1 built (calendar RSVP, events store, tab skeleton, topics, clashes, archive). Known rough edge: an umbrella entry that spans several days (e.g. a forum) clashes with the sessions inside it; to refine.

- 5.2 built: Club Diplomatique subjects, Luma, organiser registrations, Genève internationale tables; evidence-based status; merging across sources; helper `sync-events` + agent step. First real run: 1,649 event-related messages in the year, about 600 events in the archive; about 1,500 emails kept as candidates for the model step (mostly noise: prioritise non-bulk, direct, personal invitations).

## Rules that stay
Drafts only, never send; inbox-derived data local only (S2); public data S0; one model door (gateway, new job `event_extract`); no real data in the repo; nothing in her files changes; calendar stays read-only.

## Decisions (Anne-Marie, 2 Oct 2026)
1. Tab name: **Geneva and beyond**.
2. Sources: **both** the public pages and the emails.
3. Topics: digital and AI governance, cyber, peacebuilding, humanitarian tech, multilateral diplomacy, **harmful information (and all its analogues: mis/disinformation, hate speech, information integrity)**, **technology for good**; more can be added.
4. Default view: upcoming events, with the past year as a **searchable archive**.
5. Push the plan commit and start on slice 5.1: approved.

## Original open decisions
1. Tab name: "Events" with a Geneva filter, or keep "Geneva"?
2. Public listings: fetch the public pages (slice 5.4), or rely only on the newsletters already in her inbox?
3. Topics of interest, to rank and filter (e.g. digital and AI governance, cyber, peacebuilding, humanitarian tech, multilateral diplomacy).
4. Show only upcoming events by default, with the past year as an archive?
