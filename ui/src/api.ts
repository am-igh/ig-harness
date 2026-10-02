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
