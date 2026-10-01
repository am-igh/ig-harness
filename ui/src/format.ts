const TZ = "Europe/Zurich";
const d = (iso: string) => new Date(iso.length === 10 ? iso + "T12:00:00" : iso);

export const dayShort = (iso: string) =>
  new Intl.DateTimeFormat("en-GB", { weekday: "short", day: "numeric", month: "short", timeZone: iso.length === 10 ? undefined : TZ }).format(d(iso)).replace(",", "");
export const dayMonth = (iso: string) =>
  new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short" }).format(d(iso));
export const dayFull = (iso: string) =>
  new Intl.DateTimeFormat("en-GB", { weekday: "long", day: "numeric", month: "long", year: "numeric" }).format(d(iso));
export const headerDate = (nowIso: string) => {
  const t = new Date(nowIso);
  const day = new Intl.DateTimeFormat("en-GB", { weekday: "long", day: "numeric", month: "long", timeZone: TZ }).format(t);
  const hm = new Intl.DateTimeFormat("en-GB", { hour: "2-digit", minute: "2-digit", timeZone: TZ }).format(t);
  return `${day} · ${hm}`;
};
export const timeOf = (iso: string) =>
  new Intl.DateTimeFormat("en-GB", { hour: "2-digit", minute: "2-digit", timeZone: TZ }).format(new Date(iso));

export const daysBetween = (aIso: string, bIso: string) =>
  Math.round((d(bIso).getTime() - d(aIso).getTime()) / 86400000);

export function dueLabel(due: string | null, overdue: number, today: string): string {
  if (!due) return "no date";
  if (overdue > 0) return `${overdue} day${overdue === 1 ? "" : "s"} overdue`;
  if (due === today) return "due today";
  return `due ${dayShort(due)}`;
}
