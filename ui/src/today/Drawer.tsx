import { useCallback, useEffect, useState } from "react";
import { type DeadlineDetail, type DoneItem, getDeadline, getDone, setDone } from "../api";
import { dayFull, dayHeading, dayShort, doneDay, doneTime } from "../format";
import { useReveal } from "./useReveal";
import ReminderDrawer from "../drafts/ReminderDrawer";
import CalendarDrawer from "../calendar/CalendarDrawer";
import NotesLogDrawer from "../notes/NotesLogDrawer";
import AuditDrawer from "../finance/AuditDrawer";
import ScansDrawer from "../finance/ScansDrawer";
import HoursDrawer from "../finance/HoursDrawer";

export type Panel = { kind: "deadline"; id: number } | { kind: "done" } | { kind: "reminder"; id: number } | { kind: "calendar" } | { kind: "notes" } | { kind: "audit" } | { kind: "scans" } | { kind: "hours" } | null;

export function Shell({ kicker, title, meta, onClose, children, wide }: {
  kicker: string; title: string; meta: string; onClose: () => void; children: React.ReactNode; wide?: boolean;
}) {
  useEffect(() => {
    const h = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [onClose]);
  return (
    <>
      <button type="button" aria-label="Close panel" className="scrim" onClick={onClose} />
      <aside className={`drawer slide ${wide ? "wide" : ""}`} role="dialog" aria-label={title}>
        <div className="drawer-head">
          <div className="drawer-kicker"><span>{kicker}</span>
            <button type="button" aria-label="Close" onClick={onClose}>✕</button></div>
          <div className="serif drawer-title">{title}</div>
          <div className="drawer-meta">{meta}</div>
        </div>
        <div className="drawer-body">{children}</div>
      </aside>
    </>
  );
}

function DeadlineDrawer({ id, today, onClose, onTick }: { id: number; today: string; onClose: () => void; onTick: () => void }) {
  const [d, setD] = useState<DeadlineDetail | null>(null);
  const [err, setErr] = useState(false);
  useEffect(() => { getDeadline(id).then(setD).catch(() => setErr(true)); }, [id]);
  if (err) return <Shell kicker="DEADLINE" title="Could not load" meta="" onClose={onClose}><p>Please try again.</p></Shell>;
  if (!d) return <Shell kicker="DEADLINE" title="Loading…" meta="" onClose={onClose}><p /></Shell>;
  const left = d.days_left;
  const facts: [string, string][] = [
    ["Due", dayFull(d.due)],
    ["In", left === 0 ? "today" : left > 0 ? `${left} day${left === 1 ? "" : "s"}` : `${-left} days overdue`],
    ["Type", d.kind === "reporting" ? "Reporting date" : d.kind === "fixed" ? "Fixed date" : "Deadline"],
    ["Weight", d.importance === "major" ? "Major" : "Hard"],
    ["Project", (d.code ?? "none") + (d.personal ? " · personal" : "")],
    ["Warnings", `D-14 on ${dayShort(d.warn_d14)}${d.warn_d14 < today ? " (passed)" : ""}; D-3 on ${dayShort(d.warn_d3)}${d.warn_d3 < today ? " (passed)" : ""}`],
    ["Source", d.source === "suivi" ? "Suivi.xlsx" : d.source === "registre" ? "Project register" : d.source],
  ];
  return (
    <Shell kicker={`DEADLINE${d.code ? " · " + d.code : ""}`} title={d.title} meta={dayFull(d.due)} onClose={onClose}>
      <div className="facts">{facts.map(([k, v]) => <><span key={k + "k"}>{k}</span><span key={k + "v"}>{v}</span></>)}</div>
      {d.related.length > 0 && (
        <div className="related"><div className="kicker">RELATED</div>
          {d.related.map((r, i) => (
            <div key={i} className="rel-row"><span className="mono rel-type">{r.type}</span><span>{r.label}</span><small>{r.meta}</small></div>
          ))}
        </div>
      )}
      {d.status === "open" && (
        <button type="button" className="btn-primary" onClick={() => { onTick(); onClose(); }}>Tick this deadline off</button>
      )}
    </Shell>
  );
}

const RANGES: [string, number][] = [["This week", 7], ["30 days", 30], ["All time", 0]];
const TYPE_LABEL: Record<string, string> = { task: "TASK", deadline: "DEADLINE", waiting_on: "WAITING", email: "EMAIL" };

function DoneDrawer({ today, onClose, onChanged }: { today: string; onClose: () => void; onChanged: () => void }) {
  const [days, setDays] = useState(7);
  const [q, setQ] = useState("");
  const [items, setItems] = useState<DoneItem[] | null>(null);
  const load = useCallback(() => getDone(days, q).then((r) => setItems(r.items)), [days, q]);
  useEffect(() => { const t = setTimeout(load, q ? 250 : 0); return () => clearTimeout(t); }, [load, q]);

  const reopen = async (i: DoneItem) => { await setDone(i, false); await load(); onChanged(); };
  const n = items?.length ?? 0;
  const groups: [string, DoneItem[]][] = [];
  for (const i of items ?? []) {
    const d = doneDay(i.done_at);
    if (groups.length && groups[groups.length - 1][0] === d) groups[groups.length - 1][1].push(i); else groups.push([d, [i]]);
  }
  return (
    <Shell kicker="DONE" title={items ? `${n} thing${n === 1 ? "" : "s"} done` : "Loading…"} meta="With the date and time you ticked them off" onClose={onClose}>
      <div className="range" role="group" aria-label="Period">
        {RANGES.map(([label, d]) => <button key={d} type="button" className={d === days ? "on" : ""} aria-pressed={d === days} onClick={() => setDays(d)}>{label}</button>)}
      </div>
      <input className="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search what you have done…" aria-label="Search done items" />
      {items && n === 0 && <p className="muted">{q ? "Nothing matches." : "Nothing ticked off in this period yet. Tick something and it will be recorded here."}</p>}
      {groups.map(([day, rows]) => (
        <div key={day} className="done-group">
          <div className="kicker">{dayHeading(day, today).toUpperCase()}</div>
          {rows.map((i) => (
            <DoneRow key={i.key + i.done_at} i={i} onReopen={reopen} />
          ))}
        </div>
      ))}
    </Shell>
  );
}

function DoneRow({ i, onReopen }: { i: DoneItem; onReopen: (i: DoneItem) => void }) {
  const { shown, show, hide } = useReveal(i);
  return (
            <div className="done-row">
              <span className="mono done-time">{doneTime(i.done_at) || "—"}</span>
              <span className="done-title">
                {i.masked && !shown
                  ? <button type="button" className="masked-title" onClick={show} title="Click to show the details">🔒 {i.title} <span>show details</span></button>
                  : <>{shown ? shown.title : i.title}{shown && <button type="button" className="link-quiet inline" onClick={hide}>hide</button>}</>}
              </span>
              <span className="mono rel-type">{TYPE_LABEL[i.type] ?? i.type}</span>
              {i.reopenable
                ? <button type="button" className="btn-ghost" onClick={() => onReopen(i)}>Reopen</button>
                : <small title="Closed in Suivi; reopen it there">{i.via ? `via ${i.via}` : ""}</small>}
            </div>
  );
}

export default function Drawer({ panel, today, onClose, onTickDeadline, onChanged }: {
  panel: Panel; today: string; onClose: () => void; onTickDeadline: (id: number) => void; onChanged: () => void;
}) {
  if (!panel) return null;
  if (panel.kind === "done") return <DoneDrawer today={today} onClose={onClose} onChanged={onChanged} />;
  if (panel.kind === "reminder") return <ReminderDrawer waitingId={panel.id} onClose={onClose} />;
  if (panel.kind === "calendar") return <CalendarDrawer today={today} onClose={onClose} />;
  if (panel.kind === "notes") return <NotesLogDrawer today={today} onClose={onClose} onChanged={onChanged} />;
  if (panel.kind === "hours") return <HoursDrawer onClose={onClose} />;
  if (panel.kind === "scans") return <ScansDrawer onClose={onClose} onChanged={onChanged} />;
  if (panel.kind === "audit") return <AuditDrawer initial={null} onClose={onClose} onChanged={onChanged} />;
  return <DeadlineDrawer id={panel.id} today={today} onClose={onClose} onTick={() => onTickDeadline(panel.id)} />;
}
