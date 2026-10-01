export type Item = {
  key: string; type: "task" | "deadline" | "waiting_on"; id: number; title: string;
  code: string | null; weight: "major" | "hard" | "soft" | "waiting"; person: string | null;
  personal: boolean; due: string | null; days_overdue: number; done: boolean;
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
export type DoneItem = { title: string; done_at: string; personal: boolean };

async function j<T>(url: string, init?: RequestInit): Promise<T> {
  const r = await fetch(url, init);
  if (!r.ok) throw new Error(`${url}: ${r.status}`);
  return r.json();
}
export const getToday = () => j<Today>("/api/today");
export const getDeadline = (id: number) => j<DeadlineDetail>(`/api/deadlines/${id}`);
export const getDoneWeek = () => j<{ items: DoneItem[] }>("/api/done/week");
export const setDone = (it: Pick<Item, "type" | "id">, done: boolean) =>
  j<{ changed: boolean }>(`/api/items/${it.type}/${it.id}/${done ? "done" : "undo"}`, { method: "POST" });
