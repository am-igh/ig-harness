import { useCallback, useEffect, useState } from "react";
import { type HoursWeek, getHours } from "../api";
import { dayShort } from "../format";
import { Shell } from "../today/Drawer";

export function useHours() {
  const [w, setW] = useState<HoursWeek | null>(null);
  const load = useCallback(() => getHours().then(setW).catch(() => setW(null)), []);
  useEffect(() => { load(); const t = setInterval(load, 60_000); return () => clearInterval(t); }, [load]);
  return w;
}

/** The "Hours this week" widget, read from hours.csv. */
export function HoursTile({ w, onOpen }: { w: HoursWeek | null; onOpen: () => void }) {
  const head = !w ? "—" : w.has_any || w.total > 0 ? `${w.total} h` : "No hours yet";
  const sub = !w ? "Checking…" : w.by_project.length ? w.by_project.map((p) => `${p.project} ${p.hours}`).join(" · ") : "Nothing logged this week";
  return (
    <button type="button" className="tile tile-live" onClick={onOpen} aria-label="Open hours this week">
      <div className="tile-art cal-art"><span className="cal-art-dow">week</span><span className="serif cal-art-day">{w ? Math.round(w.total) : "·"}</span></div>
      <div className="tile-text"><span className="tile-title">Hours this week</span><span className="serif tile-head">{head}</span><span className="tile-sub">{sub}</span>
        <span className={`soon ${w && w.flagged > 0 ? "warn" : ""}`}>{w && w.flagged > 0 ? `${w.flagged} entr${w.flagged === 1 ? "y" : "ies"} to check →` : "Click for the detail"}</span></div>
    </button>
  );
}

export default function HoursDrawer({ onClose }: { onClose: () => void }) {
  const [w, setW] = useState<HoursWeek | null>(null);
  const go = (day?: string) => getHours(day).then(setW).catch(() => setW(null));
  useEffect(() => { go(); }, []);
  if (!w) return <Shell kicker="HOURS" title="Hours this week" meta="" onClose={onClose}><p className="muted">Loading…</p></Shell>;
  return (
    <Shell kicker="HOURS" title={`${w.total} h ${w.is_current ? "this week" : "that week"}`} meta={`${dayShort(w.week_start)} to ${dayShort(w.week_end)} · from hours.csv, read-only`} onClose={onClose} wide>
      <div className="stmt-head"><button type="button" className="btn-small" onClick={() => go(w.prev)}>← Previous week</button>
        {w.next && <button type="button" className="btn-small" onClick={() => go(w.next!)}>Next week →</button>}</div>
      {w.by_project.length > 0 && <div className="facts">{w.by_project.map((p) => <><span key={p.project}>{p.project}</span><span key={p.project + "h"}>{p.hours} h</span></>)}</div>}
      {w.days_without.length > 0 && <div className="notice"><span>No hours logged on: {w.days_without.map((d) => dayShort(d)).join(", ")}.</span></div>}
      {!w.has_any && <p className="muted">hours.csv has no entries yet.</p>}
      {w.entries.map((e, i) => (
        <div key={i} className={`scan-card ${e.problems.length ? "stmt-bad" : ""}`}>
          <div className="scan-head"><span className="mono stmt-name">{dayShort(e.date)} · {e.project ?? "?"}{e.budget_line ? ` · ${e.budget_line}` : ""}</span><span className="chip chip-soft">{e.hours ?? "?"} h</span></div>
          <div>{e.description}</div>
          <div className="stmt-detail">Evidence: {e.evidence ?? "none"}{e.entered_on ? ` · entered ${dayShort(e.entered_on)}` : ""}{e.source ? ` · ${e.source}` : ""}</div>
          {e.problems.length > 0 && <div className="warn-text">To check: {e.problems.join("; ")}</div>}
        </div>
      ))}
    </Shell>
  );
}
