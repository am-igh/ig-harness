import { useEffect, useState } from "react";
import { type DeadlineDetail, type DoneItem, getDeadline, getDoneWeek } from "../api";
import { dayFull, dayShort } from "../format";

export type Panel = { kind: "deadline"; id: number } | { kind: "done" } | null;

export function Shell({ kicker, title, meta, onClose, children }: {
  kicker: string; title: string; meta: string; onClose: () => void; children: React.ReactNode;
}) {
  useEffect(() => {
    const h = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [onClose]);
  return (
    <>
      <button type="button" aria-label="Close panel" className="scrim" onClick={onClose} />
      <aside className="drawer slide" role="dialog" aria-label={title}>
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

function DoneDrawer({ onClose }: { onClose: () => void }) {
  const [items, setItems] = useState<DoneItem[] | null>(null);
  useEffect(() => { getDoneWeek().then((r) => setItems(r.items)); }, []);
  const n = items?.length ?? 0;
  return (
    <Shell kicker="DONE THIS WEEK" title={items ? `${n} thing${n === 1 ? "" : "s"} off your plate` : "Loading…"} meta="Since Monday" onClose={onClose}>
      {items && n === 0 && <p className="muted">Nothing ticked off yet this week. Tick something in Today &amp; overdue and the jet will rise.</p>}
      {items?.map((i, k) => (
        <div key={k} className="done-row">✓ <span>{i.title}</span><small>{dayShort(i.done_at.slice(0, 10))}</small></div>
      ))}
    </Shell>
  );
}

export default function Drawer({ panel, today, onClose, onTickDeadline }: {
  panel: Panel; today: string; onClose: () => void; onTickDeadline: (id: number) => void;
}) {
  if (!panel) return null;
  if (panel.kind === "done") return <DoneDrawer onClose={onClose} />;
  return <DeadlineDrawer id={panel.id} today={today} onClose={onClose} onTick={() => onTickDeadline(panel.id)} />;
}
