// Pure calendar logic: dates as "YYYY-MM-DD" strings, no timezone surprises. Tested in layout.test.ts.
export type View = "day" | "week" | "month";
export type Ev = { start: string; end: string | null; all_day: boolean };
export type Seg = { id: number; startMin: number; endMin: number };

const MS = 86400000;
const utc = (day: string) => { const [y, m, d] = day.split("-").map(Number); return Date.UTC(y, m - 1, d); };
export const fromUtc = (t: number) => new Date(t).toISOString().slice(0, 10);

export const addDays = (day: string, n: number) => fromUtc(utc(day) + n * MS);
export const daysBetween = (a: string, b: string) => Math.round((utc(b) - utc(a)) / MS);
/** Monday = 0 … Sunday = 6 */
export const weekday = (day: string) => (new Date(utc(day)).getUTCDay() + 6) % 7;
export const startOfWeek = (day: string) => addDays(day, -weekday(day));
export const firstOfMonth = (day: string) => day.slice(0, 8) + "01";

/** Six full weeks starting on the Monday on or before the 1st: the month grid. */
export function monthGrid(anchor: string): string[] {
  const first = startOfWeek(firstOfMonth(anchor));
  return Array.from({ length: 42 }, (_, i) => addDays(first, i));
}

export function rangeFor(view: View, anchor: string): { start: string; end: string } {
  if (view === "day") return { start: anchor, end: anchor };
  if (view === "week") { const s = startOfWeek(anchor); return { start: s, end: addDays(s, 6) }; }
  const g = monthGrid(anchor);
  return { start: g[0], end: g[41] };
}

/** Previous / next period. Month steps land on the 1st so 31 Oct + 1 month is 1 Nov, never 3 Dec. */
export function shift(view: View, anchor: string, dir: 1 | -1): string {
  if (view === "day") return addDays(anchor, dir);
  if (view === "week") return addDays(anchor, 7 * dir);
  const [y, m] = anchor.split("-").map(Number);
  const t = new Date(Date.UTC(y, m - 1 + dir, 1));
  return t.toISOString().slice(0, 10);
}

const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
const DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];
export const dayName = (day: string) => DAYS[weekday(day)];
export const monthName = (day: string) => MONTHS[Number(day.slice(5, 7)) - 1];
export const dayOfMonth = (day: string) => Number(day.slice(8, 10));

export function title(view: View, anchor: string): string {
  if (view === "month") return `${monthName(anchor)} ${anchor.slice(0, 4)}`;
  if (view === "day") return `${dayName(anchor)} ${dayOfMonth(anchor)} ${monthName(anchor)} ${anchor.slice(0, 4)}`;
  const s = startOfWeek(anchor), e = addDays(s, 6);
  return s.slice(0, 7) === e.slice(0, 7) ? `${dayOfMonth(s)}–${dayOfMonth(e)} ${monthName(e)} ${e.slice(0, 4)}`
    : `${dayOfMonth(s)} ${monthName(s).slice(0, 3)} – ${dayOfMonth(e)} ${monthName(e).slice(0, 3)} ${e.slice(0, 4)}`;
}

/** Date and minutes-since-midnight of an instant, in Geneva time (whatever the browser's own zone is). */
export function genevaParts(iso: string, tz = "Europe/Zurich"): { date: string; minutes: number } {
  const f = new Intl.DateTimeFormat("en-CA", { timeZone: tz, year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hourCycle: "h23" });
  const p: Record<string, string> = {};
  for (const x of f.formatToParts(new Date(iso))) p[x.type] = x.value;
  return { date: `${p.year}-${p.month}-${p.day}`, minutes: Number(p.hour) * 60 + Number(p.minute) };
}

export const hhmm = (minutes: number) => `${String(Math.floor(minutes / 60)).padStart(2, "0")}:${String(minutes % 60).padStart(2, "0")}`;

/** Every calendar day an event covers. All-day events end the day BEFORE their stored end date. */
export function daysCovered(e: Ev, tz = "Europe/Zurich"): string[] {
  if (e.all_day) {
    const last = e.end ? addDays(e.end.slice(0, 10), -1) : e.start.slice(0, 10);
    const first = e.start.slice(0, 10);
    return Array.from({ length: Math.min(60, Math.max(1, daysBetween(first, last) + 1)) }, (_, i) => addDays(first, i));
  }
  const s = genevaParts(e.start, tz);
  const en = e.end ? genevaParts(e.end, tz) : s;
  const lastDay = en.minutes === 0 && en.date > s.date ? addDays(en.date, -1) : en.date;     // ending at midnight belongs to the day before
  return Array.from({ length: Math.min(60, Math.max(1, daysBetween(s.date, lastDay) + 1)) }, (_, i) => addDays(s.date, i));
}

/** The part of a timed event that falls on `day`, as minutes since midnight. */
export function segmentFor(e: Ev, day: string, tz = "Europe/Zurich"): { startMin: number; endMin: number } | null {
  if (e.all_day || !daysCovered(e, tz).includes(day)) return null;
  const s = genevaParts(e.start, tz);
  const en = e.end ? genevaParts(e.end, tz) : { date: s.date, minutes: s.minutes + 30 };
  const startMin = s.date === day ? s.minutes : 0;
  let endMin = en.date === day ? en.minutes : 1440;
  if (en.date > day) endMin = 1440;
  return { startMin, endMin: Math.max(endMin, startMin + 20) };       // very short events still get a readable block
}

/** Side-by-side columns for overlapping events: id -> {col, cols}. */
export function layoutColumns(segs: Seg[]): Map<number, { col: number; cols: number }> {
  const out = new Map<number, { col: number; cols: number }>();
  const sorted = [...segs].sort((a, b) => a.startMin - b.startMin || b.endMin - a.endMin);
  let cluster: Seg[] = [], clusterEnd = -1;
  const flush = () => {
    const lanes: number[] = [];                                       // end minute of the last event in each lane
    const placed = new Map<number, number>();
    for (const s of cluster) {
      let lane = lanes.findIndex((end) => end <= s.startMin);
      if (lane < 0) { lane = lanes.length; lanes.push(0); }
      lanes[lane] = s.endMin;
      placed.set(s.id, lane);
    }
    for (const s of cluster) out.set(s.id, { col: placed.get(s.id)!, cols: lanes.length });
    cluster = [];
  };
  for (const s of sorted) {
    if (cluster.length && s.startMin >= clusterEnd) flush();
    cluster.push(s);
    clusterEnd = cluster.length === 1 ? s.endMin : Math.max(clusterEnd, s.endMin);
  }
  if (cluster.length) flush();
  return out;
}
