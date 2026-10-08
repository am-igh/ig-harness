import { useState } from "react";
import { type HoursAsk, logHours, setHoursPrompt } from "../api";

const addDays = (iso: string, n: number) => { const d = new Date(iso + "T12:00:00"); d.setDate(d.getDate() + n); return d.toISOString().slice(0, 10); };

/** Appears after you tick off a to-do that belongs to a project: how long did it take, and on which day(s)? Your click on "Log hours" is the approval; the entries are appended to hours.csv by the Mac-side writer. */
export default function HoursPrompt({ item, info, onClose, onLogged }: { item: { type: string; id: number }; info: HoursAsk; onClose: () => void; onLogged: () => void }) {
  const [rows, setRows] = useState([{ date: info.date ?? new Date().toISOString().slice(0, 10), hours: "" }]);
  const [desc, setDesc] = useState(info.title ?? "");
  const [err, setErr] = useState(""); const [busy, setBusy] = useState(false); const [done, setDone] = useState<string | null>(null);
  const today = new Date().toISOString().slice(0, 10);
  const submit = async () => {
    setErr(""); setBusy(true);
    try {
      const r = await logHours(item.type, item.id, rows.map((x) => ({ date: x.date, hours: x.hours })), desc);
      setDone(`Logged ${r.hours} h on ${r.project}. ${r.queued ? "It is added to hours.csv at the next refresh (or press ↻)." : "It is in this week's hours."}`);
      onLogged(); setTimeout(onClose, 4500);
    } catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
  };
  return (
    <aside className="hours-prompt" role="dialog" aria-label="Log time for this to-do">
      {done ? <div>{done}</div> : <>
        <div className="kicker">HOURS ON {info.project}</div>
        <div className="hp-title">How long did “{info.title}” take?</div>
        {(info.already_logged ?? 0) > 0 && <div className="small muted">{info.already_logged} h already logged for this to-do.</div>}
        {rows.map((r, i) => (
          <div key={i} className="hp-row">
            <input type="date" value={r.date} max={today} onChange={(e) => setRows(rows.map((x, j) => (j === i ? { ...x, date: e.target.value } : x)))} aria-label="Day" />
            <input type="number" min="0.25" max="14" step="0.25" value={r.hours} placeholder="hours" autoFocus={i === rows.length - 1} onChange={(e) => setRows(rows.map((x, j) => (j === i ? { ...x, hours: e.target.value } : x)))} aria-label="Hours" />
            {rows.length > 1 && <button type="button" className="btn-ghost" onClick={() => setRows(rows.filter((_, j) => j !== i))} aria-label="Remove this day">✕</button>}
          </div>))}
        {rows.length < 10 && <button type="button" className="btn-ghost hp-add" onClick={() => setRows([...rows, { date: addDays(rows[rows.length - 1].date, -1), hours: "" }])}>+ another day</button>}
        <input className="hp-desc" value={desc} onChange={(e) => setDesc(e.target.value)} aria-label="What it was" placeholder="What you did" />
        {err && <div className="edit-err">{err}</div>}
        <div className="hp-actions">
          <button type="button" className="btn-primary" disabled={busy || rows.some((r) => !r.hours)} onClick={submit}>Log hours</button>
          <button type="button" className="btn-ghost" onClick={onClose}>Not now</button>
          <button type="button" className="btn-ghost small" onClick={() => setHoursPrompt(false).finally(onClose)} title="You can turn it on again later">Stop asking</button>
        </div>
      </>}
    </aside>
  );
}
