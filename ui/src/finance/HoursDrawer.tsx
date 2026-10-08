import { useCallback, useEffect, useState } from "react";
import { type HourProposal, type HoursWeek, approveHourPass, editHourPass, findHourPass, getHourPass, getHours, getProjects, skipHourPass } from "../api";
import { dayShort } from "../format";
import { Shell } from "../today/Drawer";

export function useHours() {
  const [w, setW] = useState<HoursWeek | null>(null);
  const load = useCallback(() => getHours().then(setW).catch(() => setW(null)), []);
  useEffect(() => { load(); const t = setInterval(load, 60_000); window.addEventListener("hours-changed", load); return () => { clearInterval(t); window.removeEventListener("hours-changed", load); }; }, [load]);
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

function Proposal({ p, projects, onChanged }: { p: HourProposal; projects: string[]; onChanged: () => void }) {
  const [hours, setHours] = useState(p.hours == null ? "" : String(p.hours));
  const [desc, setDesc] = useState(p.description ?? "");
  const [err, setErr] = useState("");
  const save = async (f: Parameters<typeof editHourPass>[1]) => { setErr(""); try { await editHourPass(p.id, f); } catch (e) { setErr((e as Error).message); } };
  const act = async (fn: () => Promise<unknown>) => { setErr(""); try { await fn(); } catch (e) { setErr((e as Error).message); } onChanged(); };
  const open = p.status === "proposed";
  return (
    <div className={`scan-card ${p.status === "failed" ? "stmt-bad" : ""}`}>
      <div className="scan-head"><span className="mono stmt-name">{dayShort(p.date)}</span><span className="chip chip-soft">{({ proposed: "Suggested", approved: "Adding…", written: "Added", failed: "Not added", skipped: "Skipped" } as Record<string, string>)[p.status]}</span></div>
      {open ? (
        <div className="scan-fields">
          <label className="scan-field"><span>Project</span><select defaultValue={p.project ?? ""} onChange={(e) => save({ project: e.target.value })}>{projects.map((c) => <option key={c}>{c}</option>)}</select></label>
          <label className="scan-field"><span>Hours</span><input value={hours} inputMode="decimal" placeholder="e.g. 1.5" onChange={(e) => setHours(e.target.value)} onBlur={() => save({ hours })} /></label>
          <label className="scan-field" style={{ gridColumn: "span 3" }}><span>Description</span><input value={desc} onChange={(e) => setDesc(e.target.value)} onBlur={() => save({ description: desc })} /></label>
        </div>
      ) : <div>{p.project} · {p.hours} h · {p.description}</div>}
      <div className="stmt-detail">Evidence: {p.evidence}{open && p.basis ? ` · Hours: ${p.basis}` : ""}</div>
      {open && <div className="stmt-actions"><button type="button" className="btn-primary" onClick={() => act(async () => { await save({ hours, description: desc }); await approveHourPass(p.id); })}>Add to hours.csv</button>
        <button type="button" className="btn-ghost" onClick={() => act(() => skipHourPass(p.id))}>Skip</button></div>}
      {p.status === "written" && <span className="stmt-ok">✓ Added to hours.csv</span>}
      {p.status === "failed" && <span className="warn-text">Not added: {p.result}</span>}
      {err && <div className="edit-err">{err}</div>}
    </div>
  );
}

export default function HoursDrawer({ onClose }: { onClose: () => void }) {
  const [w, setW] = useState<HoursWeek | null>(null);
  const [pass, setPass] = useState<HourProposal[]>([]);
  const [projects, setProjects] = useState<string[]>([]);
  const [note, setNote] = useState("");
  const loadPass = useCallback((day?: string) => getHourPass(day).then((r) => setPass(r.items)).catch(() => undefined), []);
  const go = (day?: string) => { getHours(day).then(setW).catch(() => setW(null)); loadPass(day); };
  useEffect(() => { go(); getProjects().then((r) => setProjects(r.projects.map((p) => p.code))).catch(() => undefined); }, []);   // eslint-disable-line react-hooks/exhaustive-deps
  const waiting = pass.some((p) => p.status === "approved");
  useEffect(() => { if (!waiting || !w) return; const t = setInterval(() => go(w.week_start), 3000); return () => clearInterval(t); }, [waiting, w?.week_start]);   // eslint-disable-line react-hooks/exhaustive-deps
  const find = async () => { if (!w) return; const r = await findHourPass(w.week_start); setNote(r.added ? `${r.added} suggestion${r.added === 1 ? "" : "s"} found.` : "Nothing new to suggest."); loadPass(w.week_start); };
  if (!w) return <Shell kicker="HOURS" title="Hours this week" meta="" onClose={onClose}><p className="muted">Loading…</p></Shell>;
  return (
    <Shell kicker="HOURS" title={`${w.total} h ${w.is_current ? "this week" : "that week"}`} meta={`${dayShort(w.week_start)} to ${dayShort(w.week_end)} · from hours.csv, read-only`} onClose={onClose} wide>
      <div className="stmt-head"><button type="button" className="btn-small" onClick={() => go(w.prev)}>← Previous week</button>
        {w.next && <button type="button" className="btn-small" onClick={() => go(w.next!)}>Next week →</button>}</div>
      {w.by_project.length > 0 && <div className="facts">{w.by_project.map((p) => <><span key={p.project}>{p.project}</span><span key={p.project + "h"}>{p.hours} h</span></>)}</div>}
      {w.days_without.length > 0 && <div className="notice"><span>No hours logged on: {w.days_without.map((d) => dayShort(d)).join(", ")}.</span></div>}
      {!w.has_any && <p className="muted">hours.csv has no entries yet.</p>}
      <div className="related"><div className="kicker">FRIDAY PASS: SUGGESTED ENTRIES</div>
        <div className="note">Suggestions come from your Suivi journal and from calendar events tagged like [TK]. Nothing is invented: if no hours are known, you enter your estimate. Each entry needs your approval, and is added to the end of hours.csv with its evidence pointer.</div>
        <div className="stmt-head"><button type="button" className="btn-small" onClick={find}>Find hours for this week</button>{note && <span className="muted">{note}</span>}</div>
        {pass.map((p) => <Proposal key={p.id} p={p} projects={projects} onChanged={() => go(w.week_start)} />)}
      </div>
      <div className="kicker">IN hours.csv THIS WEEK</div>
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
