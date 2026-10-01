export type Item = {
  key: string; type: "task" | "deadline" | "waiting_on" | "email"; id: number; title: string;
  code: string | null; weight: "major" | "hard" | "soft" | "waiting"; person: string | null;
  personal: boolean; due: string | null; days_overdue: number; done: boolean; done_at: string | null;
};
export type Mark = {
  id: number; title: string; due: string; importance: "major" | "normal"; kind: string;
  code: string | null; personal: boolean; warning: string | null;
};
export type CalEvent = { id: number; title: string; start: string; end: string | null; all_day: boolean };
export type Today = {
  now: string; today: string; week_start: string; done_this_week: number;
  today_items: Item[]; upcoming_items: Item[]; undated_tasks: number;
  lake: Mark[]; ticks: string[]; events_today: CalEvent[]; next_event: { title: string; start: string } | null;
};
export type DeadlineDetail = {
  id: number; title: string; due: string; kind: string; importance: string; code: string | null;
  status: string; personal: boolean; source: string; days_left: number; warn_d14: string; warn_d3: string;
  related: { type: string; label: string; meta: string }[];
};
export type DoneItem = { key: string; type: Item["type"]; id: number; title: string; done_at: string; personal: boolean; reopenable: boolean; via: string | null };

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
  action: string | null; deadline: string | null; user_label: "yes" | "no" | null; task_id: number | null; handled_at: string | null;
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
