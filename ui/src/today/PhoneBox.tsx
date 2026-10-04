import { useCallback, useEffect, useState } from "react";
import { type PhoneList, type PhoneTodo, acceptPhone, dismissPhone, getPhone, revealPhone } from "../api";
import { dayShort } from "../format";

function Row({ t, onDone }: { t: PhoneTodo; onDone: () => void }) {
  const [text, setText] = useState(t.text);
  const [due, setDue] = useState(t.due_date ?? "");
  const [code, setCode] = useState(t.project_code ?? "");
  const [masked, setMasked] = useState(t.masked);
  const [err, setErr] = useState("");
  const show = async () => { const d = await revealPhone(t.id); setText(d.text); setCode(d.project_code ?? ""); setMasked(false); };
  const add = async () => { setErr(""); try { await acceptPhone(t.id, { text, due_date: due || null, project_code: code || null }); onDone(); } catch (e) { setErr((e as Error).message); } };
  return (
    <div className="phone-row">
      <div className="phone-main">
        {masked ? <button type="button" className="btn-ghost" onClick={show}>🔒 Personal to-do · show</button>
          : <input className="phone-text" value={text} onChange={(e) => setText(e.target.value)} aria-label="To-do" />}
        <input className="phone-due" type="date" value={due} onChange={(e) => setDue(e.target.value)} aria-label="Due date" title={due ? dayShort(due) : "No date yet: today"} />
        {!masked && t.space === "work" && <input className="phone-code" value={code} placeholder="project" onChange={(e) => setCode(e.target.value.toUpperCase())} maxLength={8} aria-label="Project code" />}
        <button type="button" className="btn-primary" onClick={add} disabled={masked}>Add to Today</button>
        <button type="button" className="btn-ghost" onClick={async () => { await dismissPhone(t.id); onDone(); }}>Dismiss</button>
      </div>
      {err && <div className="edit-err">{err}</div>}
    </div>
  );
}

/** A short list of to-dos dictated on the phone, waiting for her confirmation. Shows nothing when there is nothing to confirm (and a hint if the list cannot be read). */
export default function PhoneBox({ onChanged }: { onChanged: () => void }) {
  const [d, setD] = useState<PhoneList | null>(null);
  const load = useCallback(() => getPhone().then(setD).catch(() => setD(null)), []);
  useEffect(() => { load(); const t = setInterval(load, 60_000); return () => clearInterval(t); }, [load]);
  if (!d) return null;
  if (d.items.length === 0) {
    return d.error && d.fetched_at ? <div className="phone-hint">Phone to-dos: {d.error.startsWith("no list") ? `create a list called “${d.list ?? "Harness"}” in Reminders on your phone or Mac.` : d.error}</div> : null;
  }
  return (
    <section className="phone-box" aria-label="From your phone">
      <div className="panel-head"><h3 className="serif">From your phone <span className="chip chip-soft">{d.items.length}</span></h3><span className="muted">confirm each one, or dismiss it</span></div>
      {d.items.map((t) => <Row key={t.id} t={t} onDone={() => { load(); onChanged(); }} />)}
    </section>
  );
}
