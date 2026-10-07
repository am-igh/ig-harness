export type Item = {
  key: string; type: "task" | "deadline" | "waiting_on" | "email"; id: number; title: string;
  code: string | null; weight: "major" | "hard" | "soft" | "waiting"; person: string | null;
  personal: boolean; due: string | null; days_overdue: number; done: boolean; done_at: string | null; masked: boolean; from_note: boolean; note_count: number;
  edited: null | { title: string | null; due: string | null; title_changed: boolean; due_changed: boolean };
};
export type Mark = {
  id: number; title: string; due: string; importance: "major" | "normal"; kind: string;
  code: string | null; personal: boolean; masked: boolean; warning: string | null;
};
export type CalEvent = { id: number; title: string; start: string; end: string | null; all_day: boolean };
export type Today = {
  now: string; today: string; week_start: string; done_this_week: number;
  today_items: Item[]; upcoming_items: Item[]; later_items: Item[]; undated_tasks: number;
  lake: Mark[]; ticks: string[]; events_today: CalEvent[]; next_event: { title: string; start: string } | null;
};
export type DeadlineDetail = {
  id: number; title: string; due: string; kind: string; importance: string; code: string | null;
  status: string; personal: boolean; source: string; days_left: number; warn_d14: string; warn_d3: string;
  related: { type: string; label: string; meta: string }[];
};
export type DoneItem = { key: string; type: Item["type"]; id: number; title: string; done_at: string; personal: boolean; masked: boolean; reopenable: boolean; via: string | null };

async function j<T>(url: string, init?: RequestInit): Promise<T> {
  const r = await fetch(url, init);
  if (!r.ok) throw new Error(`${url}: ${r.status}`);
  return r.json();
}
export const getToday = () => j<Today>("/api/today");
export const getDeadline = (id: number) => j<DeadlineDetail>(`/api/deadlines/${id}`);
export const getDone = (days: number, q: string) => j<{ items: DoneItem[] }>(`/api/done?days=${days}&q=${encodeURIComponent(q)}`);
export const setDone = (it: Pick<Item, "type" | "id">, done: boolean) =>
  j<{ changed: boolean }>(`/api/items/${it.type}/${it.id}/${done ? "done" : "undo"}`, { method: "POST" });

export type Email = {
  id: number; thread_id: string; subject: string; from_name: string; from_email: string; known: boolean;
  org: string | null; role: string | null; why: string | null; urgency: number | null; received_at: string;
  snippet: string | null; hours_ago: number; direct: boolean; status: string;
  action: string | null; deadline: string | null; user_label: "yes" | "no" | null; task_id: number | null; handled_at: string | null; last_from_me: boolean; note_count: number;
};
export type EmailsResponse = {
  needs_reply: Email[]; not_needing_reply?: Email[]; handled?: Email[];
  counts: { pending: number; skipped: number; done: number; error: number };
};
export type TriageStatus = { running: boolean; last: Record<string, number | string> | null; finished_at: string | null };
export const getEmails = (hours: number, full: boolean) =>
  j<EmailsResponse>(`/api/emails?hours=${hours}&include_skipped=${full}`);
export const getTriageStatus = () => j<TriageStatus>("/api/triage/status");
export const runTriage = () => j<TriageStatus>("/api/triage/run", { method: "POST" });

export const labelEmail = (id: number, label: "yes" | "no" | null) =>
  j<{ ok: boolean }>(`/api/emails/${id}/label`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ label }) });
export const emailToTask = (id: number) => j<{ task_id: number; created: boolean }>(`/api/emails/${id}/task`, { method: "POST" });
export const redoTriage = () => j<TriageStatus>("/api/triage/run?redo=true", { method: "POST" });

export type Rule = { id: number; text: string };
export const getRules = () => j<{ items: Rule[] }>("/api/triage/rules");
export const addRule = (text: string) => j<{ id: number }>("/api/triage/rules", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text }) });
export const deleteRule = (id: number) => j<{ changed: boolean }>(`/api/triage/rules/${id}`, { method: "DELETE" });

export type ModelResult = { n: number; failed: number; tp: number; fp: number; fn: number; tn: number; accuracy: number | null; precision: number | null; recall: number | null; seconds_per_email: number | null; first_call_seconds: number | null };
export type Scoreboard = {
  running: boolean; n_labelled: number; n_yes: number;
  latest: null | { id: number; status: string; started_at: string; finished_at: string | null; error: string | null;
    results: null | { n_labelled: number; n_model_cases: number; rule_misses: number; models: Record<string, ModelResult> } };
};
export const getScoreboard = () => j<Scoreboard>("/api/scoreboard");
export const runScoreboard = (models: string[]) => j<{ started: boolean }>("/api/scoreboard/run", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ models }) });
export type GatewayStatus = { local: { up: boolean; model: string; model_installed: boolean; installed: string[] } };
export const getGatewayStatus = () => j<GatewayStatus>("/api/gateway/status");

export type ModelsInfo = {
  local: { up: boolean; models: { name: string; size_gb: number }[] };
  jobs: { job: string; label: string; tier: string; local_only: boolean; provider: string; model: string; model_installed: boolean }[];
  external: { provider: string; label: string; hosting: string; tiers: string; status: string; note: string }[];
  spend: number; cap_chf: number; budget_state: string;
};
export const getModels = () => j<ModelsInfo>("/api/models");
export const selectModel = (job: string, provider: string, model: string) =>
  j<{ ok: boolean }>("/api/models/select", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ job, provider, model }) });

export const editItem = (it: Pick<Item, "type" | "id">, patch: { title?: string; due?: string | null; reset?: boolean }) =>
  fetch(`/api/items/${it.type}/${it.id}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(patch) })
    .then(async (r) => { if (!r.ok) throw new Error((await r.json().catch(() => ({ detail: "Could not save" }))).detail); return r.json(); });

export type Revealed = { title: string; code: string | null; person: string | null };
export const reveal = (it: Pick<Item, "type" | "id">) => j<Revealed>(`/api/items/${it.type}/${it.id}/reveal`);

export type Profile = {
  person_email: string; name: string | null; org: string | null; role: string | null;
  language: string | null; formality: "formal" | "informal" | "neutral" | null; pronoun: string | null;
  greeting: string | null; closing: string | null; avg_words: number | null;
  n_mine: number; n_theirs: number; n_threads: number; confidence: "none" | "low" | "medium" | "high";
  notes: string | null; source: "learned" | "edited";
};
export const getProfiles = () => j<{ items: Profile[] }>("/api/style/profiles");
export const patchProfile = (email: string, patch: Partial<Pick<Profile, "language" | "formality" | "pronoun" | "greeting" | "closing" | "notes">>) =>
  fetch(`/api/style/profiles/${encodeURIComponent(email)}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(patch) })
    .then(async (r) => { if (!r.ok) throw new Error((await r.json().catch(() => ({ detail: "Could not save" }))).detail); return r.json(); });
export const relearnProfile = (email: string) => j<Record<string, number>>(`/api/style/profiles/${encodeURIComponent(email)}/relearn`, { method: "POST" });
export type Signature = { signature: string; source: string; learned: string | null };
export const getSignature = () => j<Signature>("/api/style/signature");
export const putSignature = (signature: string) => j<{ ok: boolean }>("/api/style/signature", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ signature }) });

export type Draft = {
  id: string; kind: "reply" | "reminder" | "new"; email_id: number | null; waiting_on_id: number | null; thread_id: string | null;
  to: string[]; cc: string[]; subject: string; body: string; language: string | null; tone: string | null; model: string | null;
  status: "draft" | "approved" | "created" | "failed" | "cancelled"; created_at: string; approved_at: string | null;
  gmail_draft_id: string | null; error: string | null; instruction: string | null; needs_input: string[];
  profile: { language?: string; tone?: string; pronoun?: string | null; greeting?: string | null; closing?: string | null; source?: string; n_mine?: number; confidence?: string; default_used?: boolean; overridden?: { tone?: boolean; language?: boolean } };
  placeholders: number; in_thread: boolean; follow_up: boolean;
};
export type DraftOpts = { tone?: string | null; language?: string | null; instruction?: string | null; thread_id?: string | null; new_message?: boolean };
async function jj<T>(url: string, init?: RequestInit): Promise<T> {
  const r = await fetch(url, init);
  if (!r.ok) throw new Error((await r.json().catch(() => ({ detail: `Error ${r.status}` }))).detail);
  return r.json();
}
const post = (body: unknown): RequestInit => ({ method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
export const getEmailDraft = (emailId: number) => jj<{ draft: Draft | null }>(`/api/emails/${emailId}/draft`);
export const makeReplyDraft = (emailId: number, o: DraftOpts) => jj<Draft>(`/api/emails/${emailId}/draft`, post(o));
export const makeReminderDraft = (wid: number, o: DraftOpts) => jj<Draft>(`/api/waiting/${wid}/draft`, post(o));
export const getDraft = (id: string) => jj<Draft>(`/api/drafts/${id}`);
export const approveDraft = (id: string, b: { body: string; subject: string; to: string[]; cc: string[] }) => jj<Draft>(`/api/drafts/${id}/approve`, post(b));
export const cancelDraft = (id: string) => jj<{ changed: boolean }>(`/api/drafts/${id}/cancel`, { method: "POST" });
export const getAgent = () => jj<{ alive: boolean }>("/api/drafts/agent");
export type ReminderThreads = { person: string; email: string; description: string; since: string; default_thread: string | null;
  threads: { thread_id: string; subject: string; last_at: string; last_from_me: number; n_messages: number }[] };
export const getReminderThreads = (wid: number) => jj<ReminderThreads>(`/api/waiting/${wid}/threads`);

export type CalEventFull = { id: number; title: string; start: string; end: string | null; all_day: boolean; tentative: boolean };
export type CalItem = { type: "deadline" | "task" | "waiting_on"; id: number; title: string; due: string; masked: boolean; importance?: string };
export type CalRange = { start: string; end: string; events: CalEventFull[]; deadlines: CalItem[]; tasks: CalItem[]; waiting: CalItem[]; coverage: { from: string | null; to: string | null } };
export const getCalendar = (start: string, end: string) => j<CalRange>(`/api/calendar?start=${start}&end=${end}`);

export type Note = {
  suivi: { state: "exported" | "pending" | "paused" | "excluded" | "none"; journal_id?: string; reason?: string };
  id: number; created_at: string; kind: "note" | "followup"; text: string; masked: boolean; personal: boolean; due_date: string | null;
  follow_up: null | { task_id: number; status: string; due: string | null; done_at: string | null };
  parent: null | { type: string; id: number; title: string; masked?: boolean };
};
export const getNotes = (type: string, id: number) => j<{ items: Note[] }>(`/api/notes?parent_type=${type}&parent_id=${id}`);
export const getNotesLog = (days: number, q: string) => j<{ items: Note[] }>(`/api/notes/log?days=${days}&q=${encodeURIComponent(q)}`);
export const addNote = (b: { text: string; kind: "note" | "followup"; parent_type?: string | null; parent_id?: number | null; due?: string | null; personal?: boolean }) => jj<Note>("/api/notes", post(b));
export const deleteNote = (id: number) => j<{ changed: boolean }>(`/api/notes/${id}`, { method: "DELETE" });
export const revealNote = (id: number) => j<{ text: string }>(`/api/notes/${id}/reveal`);

export type AuditCounts = Record<string, { n: number; total: number }>;
export type AuditLatest = { id: number; finished_at: string; n_statements: number | null; n_pieces: number | null; n_lines: number; counts: AuditCounts; debits: number; pct_ok: number | null; period_from: string | null; period_to: string | null; statements_to: string | null; accounts: string[] };
export type AuditStatus = { configured: boolean; year?: string; years: string[]; running: boolean; latest: AuditLatest | null; last_error: string | null; stale: boolean };
export type AuditLine = { compte: string; periode: string; date_raw: string; date_iso: string | null; beneficiaire: string; devise: string; montant: number; statut: string; source: string; groupe: string };
export type AuditCompare = { report_found: boolean; readable?: boolean; report?: string; report_modified?: string; same?: boolean; report_counts?: Record<string, number>; run_counts?: Record<string, number>;
  only_in_report?: { compte: string; date: string; montant: number; beneficiaire: string; statut: string }[]; only_in_run?: { compte: string; date: string; montant: number; beneficiaire: string; statut: string }[] };
export const getAuditStatus = () => j<AuditStatus>("/api/audit/status");
export const runAudit = () => jj<{ started: boolean }>("/api/audit/run", { method: "POST" });
export const getAuditLines = (statut: string) => j<{ items: AuditLine[] }>(`/api/audit/lines?statut=${encodeURIComponent(statut)}`);
export const getAuditCompare = () => j<AuditCompare>("/api/audit/compare");

// ---- Projects tab
export type RegisterInfo = { mandate: { funder: string | null; status: string | null; reporting_deadline: string | null; activity_end: string | null } | null; initiative: { status: string | null; next_touchpoint: string | null; counterpart: string | null } | null };
export type ProjectCard = { code: string; name: string; kind: "project" | "thread"; registry_link: string | null; funder: string | null; register: RegisterInfo | null; open: number; overdue: number;
  next_due: { title: string; due: string; type: string } | null; last_activity: string | null; events_ahead: number; next_event: { title: string; start: string } | null; gaps: string[] };
export type ProjectsOverview = { projects: ProjectCard[]; threads: ProjectCard[]; gaps: { code: string; name: string; gap: string }[] };
export type ProjectDetail = { code: string; name: string; kind: string; registry_link: string | null; register: RegisterInfo | null;
  items: { type: string; id: number; title: string; due: string | null; importance: string | null; days_overdue: number }[]; journal: { date: string; text: string }[]; events: { id: number; title: string; start: string }[]; gaps: string[] };
export const getProjects = () => j<ProjectsOverview>("/api/projects");
export const getProject = (code: string) => j<ProjectDetail>(`/api/projects/${encodeURIComponent(code)}`);
export type WatchName = { id: number; name: string };
export const getWatch = () => j<{ items: WatchName[] }>("/api/triage/watch");
export const addWatch = (text: string) => j<{ id: number }>("/api/triage/watch", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text }) });
export const deleteWatch = (id: number) => j<{ changed: boolean }>(`/api/triage/watch/${id}`, { method: "DELETE" });

// ---- Bank statement filing
export type Filing = { id: number; original_name: string; size: number; state: "new" | "duplicate" | "name_taken" | "same_period" | "wrong_year" | "not_statement" | "unreadable"; detail: string;
  account_label: string | null; period_from: string | null; period_to: string | null; period_kind: string | null; year: string | null; status: "staged" | "approved" | "filed" | "failed" | "skipped"; result: string | null };
export const getFilings = () => j<{ items: Filing[] }>("/api/filing");
export const approveFiling = (id: number) => j<Filing>(`/api/filing/${id}/approve`, { method: "POST" });
export const skipFiling = (id: number) => j<Filing>(`/api/filing/${id}/skip`, { method: "POST" });
export async function uploadStatement(file: File): Promise<Filing> {
  const r = await fetch("/api/filing/upload", { method: "POST", headers: { "X-Filename": encodeURIComponent(file.name), "Content-Type": "application/pdf" }, body: file });
  if (!r.ok) throw new Error((await r.json().catch(() => ({ detail: "Upload failed" }))).detail);
  return r.json();
}

// ---- Scanned invoices and receipts
export type Scan = { id: number; pages: number | null; journal_id?: string | null; source: "folder" | "upload"; original_name: string; size: number; status: "found" | "reading" | "proposed" | "duplicate" | "approved" | "filed" | "failed" | "skipped" | "unreadable";
  doc_type: string | null; type_label: string | null; supplier: string | null; number: string | null; amount: number | null; currency: string | null; doc_date: string | null; paid_date: string | null;
  folder: "Expenses" | "Income" | null; proposed_name: string | null; year: string | null; note: string | null; result: string | null };
export type ScanSummary = { to_confirm: number; reading: number; approved: number; filed_this_week: number; duplicates: number; failed: number };
export const getScans = () => j<{ items: Scan[]; summary: ScanSummary }>("/api/scans");
export const getScanSummary = () => j<ScanSummary>("/api/scans/summary");
export const editScan = (id: number, fields: Partial<Pick<Scan, "doc_type" | "supplier" | "number" | "currency" | "doc_date" | "paid_date" | "folder">> & { amount?: string | number | null }) =>
  j<Scan>(`/api/scans/${id}/edit`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(fields) });
export const approveScan = (id: number) => j<Scan>(`/api/scans/${id}/approve`, { method: "POST" });
export const skipScan = (id: number) => j<Scan>(`/api/scans/${id}/skip`, { method: "POST" });
export async function uploadScan(file: File): Promise<{ id: number; new: boolean }> {
  const r = await fetch("/api/scans/upload", { method: "POST", headers: { "X-Filename": encodeURIComponent(file.name), "Content-Type": "application/pdf" }, body: file });
  if (!r.ok) throw new Error((await r.json().catch(() => ({ detail: "Upload failed" }))).detail);
  return r.json();
}
export const splitScan = (id: number) => j<{ ids: number[] }>(`/api/scans/${id}/split`, { method: "POST" });
export const mergeScans = (ids: number[]) => j<{ id: number }>("/api/scans/merge", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ ids }) });

// ---- Hours this week
export type HourEntry = { date: string; project: string | null; budget_line: string | null; hours: number | null; description: string | null; evidence: string | null; source: string | null; entered_on: string | null; problems: string[] };
export type HoursWeek = { week_start: string; week_end: string; is_current: boolean; total: number; by_project: { project: string; hours: number }[]; entries: HourEntry[]; flagged: number; days_without: string[]; prev: string; next: string | null; has_any: boolean };
export const getHours = (day?: string) => j<HoursWeek>(`/api/hours${day ? `?day=${day}` : ""}`);

// ---- Friday hours pass
export type HourProposal = { id: number; date: string; project: string | null; budget_line: string | null; hours: number | null; description: string | null; evidence: string | null;
  source: string; basis: string | null; status: "proposed" | "approved" | "written" | "failed" | "skipped"; result: string | null };
export const getHourPass = (day?: string) => j<{ items: HourProposal[] }>(`/api/hours/pass${day ? `?day=${day}` : ""}`);
export const findHourPass = (day?: string) => j<{ added: number }>(`/api/hours/pass/find${day ? `?day=${day}` : ""}`, { method: "POST" });
export const editHourPass = (id: number, f: { hours?: string | number | null; project?: string; description?: string; budget_line?: string }) =>
  j<HourProposal>(`/api/hours/pass/${id}/edit`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(f) });
export const approveHourPass = (id: number) => j<HourProposal>(`/api/hours/pass/${id}/approve`, { method: "POST" });
export const skipHourPass = (id: number) => j<HourProposal>(`/api/hours/pass/${id}/skip`, { method: "POST" });

// ---- Project checks
export type CheckFinding = { area: string; severity: "error" | "warning" | "info"; code: string | null; message: string; count: number; refs: string[] };
export type ProjectChecks = { findings: CheckFinding[]; counts: { error: number; warning: number; info: number }; checked: { hours: number; costs: number; mandates: number }; ok: boolean };
export const getProjectChecks = () => j<ProjectChecks>("/api/projects-check");

// ---- Geneva and beyond (events)
export type EventStatus = "none" | "invited" | "interested" | "tentative" | "confirmed" | "declined";
export type EventItem = { id: number; title: string; start: string; end: string | null; all_day: boolean; venue: string | null; online: boolean; url: string | null; organizer: string | null;
  topics: string[]; geneva: boolean; relevant: boolean; tier: string; role: string | null; rsvp_by: string | null; status: EventStatus; derived_status: EventStatus; overridden: boolean; source_kind: string; hidden: boolean; clashes: number[] };
export type EventsResponse = { scope: string; items: EventItem[]; total: number; counts: { confirmed: number; tentative: number; invited: number; interested: number }; topics: string[]; other_listings: number; candidates: number };
export type EventDetail = EventItem & { evidence: { kind: string; signal: string | null; detail: string | null; observed_at: string }[]; forced: boolean };
export type EventQuery = { scope?: "upcoming" | "archive"; q?: string; status?: string; geneva?: boolean; topic?: string; allListings?: boolean };
export const getEvents = (f: EventQuery = {}) => {
  const p = new URLSearchParams();
  if (f.scope) p.set("scope", f.scope);
  if (f.q) p.set("q", f.q);
  if (f.status) p.set("status", f.status);
  if (f.geneva !== undefined) p.set("geneva", String(f.geneva));
  if (f.topic) p.set("topic", f.topic);
  if (f.allListings) p.set("all_listings", "true");
  return j<EventsResponse>(`/api/events?${p.toString()}`);
};
export const getEvent = (id: number) => j<EventDetail>(`/api/events/${id}`);
export const setEventStatus = (id: number, status: "interested" | "confirmed" | "declined" | null) =>
  j<{ ok: boolean }>(`/api/events/${id}/status`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ status }) });
export const hideEvent = (id: number, hidden = true) => j<{ ok: boolean }>(`/api/events/${id}/hide?hidden=${hidden}`, { method: "POST" });

// ---- Projects timeline (the Rhône band)
export type TimelineItem = { kind: "deadline" | "register" | "event"; id: number | null; title: string; date: string; importance: string };
export type ProjectsTimeline = { today: string; days: number; lanes: { code: string; name: string; items: TimelineItem[] }[] };
export const getProjectsTimeline = (days = 90) => j<ProjectsTimeline>(`/api/projects-timeline?days=${days}`);
export type EventsReading = { total: number; read: number; waiting: number; awaiting_text: number; gave_up: number; events_found: number; personal_waiting: number };
export const getEventsReading = () => j<EventsReading>("/api/events-reading");
export const ignoreEventSource = (id: number) => j<{ ignored: string[] }>(`/api/events/${id}/ignore-source`, { method: "POST" });

// ---- To-dos from her phone (Reminders list "Harness")
export type PhoneTodo = { id: string; text: string; due_date: string | null; project_code: string | null; space: "work" | "personal"; masked: boolean; created_at: string | null; notes: string | null };
export type PhoneList = { items: PhoneTodo[]; fetched_at: string | null; error: string | null; list: string | null };
export const getPhone = () => j<PhoneList>("/api/phone");
export const acceptPhone = (id: string, edits?: { text?: string; due_date?: string | null; project_code?: string | null; space?: "work" | "personal" }) =>
  jj<{ task_id: number; due: string }>("/api/phone/accept", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ id, ...(edits ?? {}) }) });
export const dismissPhone = (id: string) => j<{ ok: boolean }>("/api/phone/dismiss", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ id }) });
export const revealPhone = (id: string) => j<PhoneTodo>(`/api/phone/reveal?id=${encodeURIComponent(id)}`);

// ---- Morning brief
export type Brief = { day: string; created_at: string; text: string; attention_source: string; draft_status: string; draft_note: string | null };
export const getBrief = (fresh = false) => j<Brief>(`/api/brief${fresh ? "?fresh=true" : ""}`);
export type BriefDraftState = { enabled: boolean; agent_alive: boolean; status: "none" | "queued" | "saved" | "failed"; note: string | null };
export const getBriefDraft = () => j<BriefDraftState>("/api/brief/draft");
export const setBriefDraft = (on: boolean) => j<{ enabled: boolean }>("/api/brief/draft/settings", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ on }) });
export const saveBriefDraft = () => jj<{ queued: boolean }>("/api/brief/draft", { method: "POST" });

// ---- Chat box
export type CaptureProposal = { text: string; due_date: string | null; project_code: string | null; space: "work" | "personal" };
export type ChatReply = { kind: "answer" | "refused" | "unavailable"; text: string; model?: string } | { kind: "capture"; proposal: CaptureProposal };
export const askChat = (message: string) => jj<ChatReply>("/api/chat", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ message }) });
export const confirmCapture = (p: CaptureProposal) => jj<{ task_id: number; due: string }>("/api/chat/capture", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(p) });
