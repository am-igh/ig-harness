import { useCallback, useEffect, useState } from "react";
import { type PMCard, addPMProject, getPMProjects } from "../api";
import { dayShort } from "../format";
import ProjectPage from "./ProjectPage";
import { money } from "./fmt";

function Card({ p, onOpen }: { p: PMCard; onOpen: () => void }) {
  const pct = p.committed_chf ? Math.min(100, Math.round((100 * p.received_chf) / p.committed_chf)) : 0;
  return (
    <button type="button" className="proj-card pm-card" onClick={onOpen} aria-label={`Open ${p.name}`}>
      <div className="proj-top"><span className="mono proj-code">{p.code}</span>
        <span>{p.demo && <span className="pm-prop">demo</span>}{p.late_transfers > 0 && <span className="chip chip-major">{p.late_transfers} late transfer</span>}{p.overdue > 0 && <span className="chip chip-major">{p.overdue} overdue</span>}</span></div>
      <div className="serif proj-name">{p.name}</div>
      <div className="pm-chips">{p.funders.map((f) => <span key={f} className="pm-chip pm-funder">{f}</span>)}</div>
      <div className="proj-line">{money(p.received_chf)} received of {money(p.committed_chf)}</div>
      <div className="pm-bar"><i style={{ width: `${pct}%` }} /></div>
      <div className="proj-line muted">{p.next ? `Next: ${p.next.funder} ${p.next.title}, ${dayShort(p.next.due_date)}` : "No open reports"}{p.crunches ? ` · ${p.crunches} busy stretch${p.crunches === 1 ? "" : "es"}` : ""}</div>
    </button>
  );
}

function NewProject({ onDone }: { onDone: (id: number) => void }) {
  const [code, setCode] = useState(""); const [name, setName] = useState(""); const [start, setStart] = useState(""); const [end, setEnd] = useState(""); const [err, setErr] = useState("");
  return (
    <form className="pm-form pm-new" onSubmit={async (e) => { e.preventDefault(); setErr(""); try { onDone((await addPMProject({ code, name, start_date: start || undefined, end_date: end || undefined })).id); } catch (x) { setErr((x as Error).message); } }}>
      <div className="pm-form-row"><input value={code} onChange={(e) => setCode(e.target.value.toUpperCase())} placeholder="Project code" maxLength={10} aria-label="Project code" required style={{ width: 130 }} />
        <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Project name" aria-label="Project name" required />
        <label className="small muted">From <input type="date" value={start} onChange={(e) => setStart(e.target.value)} /></label>
        <label className="small muted">To <input type="date" value={end} onChange={(e) => setEnd(e.target.value)} /></label>
        <button type="submit" className="btn-primary">Create project</button></div>
      {err && <div className="edit-err">{err}</div>}
    </form>
  );
}

/** Contracts & funders: every project with its funders, contracts, requirements, reporting calendar, transfers (with the bank's exchange rate) and a funder-by-funder comparison. */
export default function ContractsTab() {
  const [list, setList] = useState<PMCard[] | null>(null);
  const [open, setOpen] = useState<number | null>(null);
  const [adding, setAdding] = useState(false);
  const load = useCallback(() => { getPMProjects().then(setList).catch(() => setList([])); }, []);
  useEffect(() => { load(); }, [load]);
  return (
    <main className="page pm-page">
      {open != null ? <ProjectPage id={open} onBack={() => { setOpen(null); load(); }} onChanged={load} /> : <>
        <div className="panel-head"><h2 className="serif">Contracts &amp; funders</h2><button type="button" className={adding ? "btn-ghost" : "btn-primary"} onClick={() => setAdding(!adding)}>{adding ? "Cancel" : "New project"}</button></div>
        <div className="sub">Funders, contracts, requirements, reporting deadlines and funding transfers for each project. Contracts stay in your folders; this page keeps where they are.</div>
        {adding && <NewProject onDone={(id) => { setAdding(false); setOpen(id); }} />}
        {list && list.length === 0 && !adding && <div className="placeholder"><b>No projects here yet</b><span>Click “New project” to add the first one, then add its funders, contracts and transfers.</span></div>}
        <div className="proj-grid">{list?.map((p) => <Card key={p.id} p={p} onOpen={() => setOpen(p.id)} />)}</div>
      </>}
    </main>
  );
}
