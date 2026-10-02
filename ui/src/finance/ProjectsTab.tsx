import { useEffect, useState } from "react";
import { type ProjectCard, type ProjectDetail, type ProjectsOverview, getProject, getProjects } from "../api";
import { dayShort } from "../format";
import { Shell } from "../today/Drawer";
import AuditDrawer from "./AuditDrawer";
import StatementsBox from "./StatementsBox";
import ScanTile from "./ScanTile";
import ScansDrawer, { useScans } from "./ScansDrawer";
import HoursDrawer, { HoursTile, useHours } from "./HoursDrawer";
import AuditTile, { useAuditStatus } from "./AuditTile";

function Card({ p, onOpen }: { p: ProjectCard; onOpen: () => void }) {
  const reg = p.register;
  return (
    <button type="button" className="proj-card" onClick={onOpen} aria-label={`Open ${p.name}`}>
      <div className="proj-top"><span className="mono proj-code">{p.code}</span>{p.overdue > 0 && <span className="chip chip-major">{p.overdue} overdue</span>}</div>
      <div className="serif proj-name">{p.name}</div>
      <div className="proj-line">{p.open === 0 ? "Nothing open" : `${p.open} open`}{p.next_due ? ` · next ${dayShort(p.next_due.due)}: ${p.next_due.title}` : ""}</div>
      <div className="proj-line muted">
        {p.last_activity ? `Last activity ${dayShort(p.last_activity)}` : "No journal entries yet"}
        {p.events_ahead > 0 && ` · ${p.events_ahead} event${p.events_ahead === 1 ? "" : "s"} ahead`}
      </div>
      {p.kind === "project" && (
        <div className="proj-line">
          {reg?.mandate ? `Funder: ${reg.mandate.funder ?? "not recorded"}` : reg?.initiative ? `Initiative · ${reg.initiative.status ?? ""}` : <span className="warn-text">Not in the project register yet</span>}
        </div>
      )}
    </button>
  );
}

function ProjectDrawer({ code, onClose }: { code: string; onClose: () => void }) {
  const [d, setD] = useState<ProjectDetail | null>(null);
  useEffect(() => { getProject(code).then(setD).catch(() => setD(null)); }, [code]);
  if (!d) return <Shell kicker="PROJECT" title={code} meta="" onClose={onClose}><p className="muted">Loading…</p></Shell>;
  const m = d.register?.mandate, i = d.register?.initiative;
  return (
    <Shell kicker={d.kind === "project" ? "PROJECT" : "THREAD"} title={d.name} meta={d.code} onClose={onClose} wide>
      {d.gaps.map((g) => <div key={g} className="notice"><span>{g}</span></div>)}
      {(m || i) && (
        <div className="facts">
          {m && <><span>Funder</span><span>{m.funder ?? "not recorded"}</span><span>Mandate</span><span>{m.status ?? "–"}{m.activity_end ? ` · to ${dayShort(m.activity_end)}` : ""}</span>
            {m.reporting_deadline && <><span>Reporting</span><span>{dayShort(m.reporting_deadline)}</span></>}</>}
          {i && <><span>Initiative</span><span>{i.status ?? "–"}</span>{i.next_touchpoint && <><span>Next touchpoint</span><span>{i.next_touchpoint}</span></>}</>}
        </div>
      )}
      <div className="related"><div className="kicker">OPEN ({d.items.length})</div>
        {d.items.length === 0 ? <p className="muted">Nothing open.</p> : d.items.map((it) => (
          <div key={`${it.type}${it.id}`} className="related-row"><span>{it.title}</span>
            <span className={it.days_overdue ? "warn-text" : "muted"}>{it.due ? (it.days_overdue ? `${it.days_overdue} d overdue` : dayShort(it.due)) : "no date"}</span></div>))}
      </div>
      {d.events.length > 0 && <div className="related"><div className="kicker">COMING UP</div>{d.events.map((e) => <div key={e.id} className="related-row"><span>{e.title}</span><span className="muted">{dayShort(e.start.slice(0, 10))}</span></div>)}</div>}
      <div className="related"><div className="kicker">RECENT JOURNAL</div>
        {d.journal.length === 0 ? <p className="muted">No entries in Suivi's journal for this code.</p> : d.journal.map((j, n) => <div key={n} className="related-row"><span>{j.text}</span><span className="muted">{dayShort(j.date)}</span></div>)}
      </div>
    </Shell>
  );
}

const SOON = [{ title: "Budget burn", sub: "Spend against each mandate" }];

export default function ProjectsTab() {
  const [data, setData] = useState<ProjectsOverview | null>(null);
  const [err, setErr] = useState(false);
  const [open, setOpen] = useState<string | null>(null);
  const [audit, setAudit] = useState(false);
  const a = useAuditStatus();
  const sc = useScans();
  const hw = useHours();
  const [hoursOpen, setHoursOpen] = useState(false);
  const [scansOpen, setScansOpen] = useState(false);
  useEffect(() => { getProjects().then(setData).catch(() => setErr(true)); }, []);
  return (
    <main className="page proj-page">
      <h2 className="serif">Projects &amp; finance</h2>
      <div className="proj-tiles">
        <AuditTile st={a.st} onOpen={() => setAudit(true)} />
        <HoursTile w={hw} onOpen={() => setHoursOpen(true)} />
        <ScanTile s={sc.data?.summary ?? null} onOpen={() => setScansOpen(true)} />
        {SOON.map((w) => <div key={w.title} className="tile"><div className="tile-art" /><div className="tile-text"><span className="tile-title">{w.title}</span><span className="serif tile-head">—</span><span className="tile-sub">{w.sub}</span><span className="soon">Coming soon</span></div></div>)}
      </div>
      <StatementsBox onFiled={a.reload} />
      <section className="card-box"><div className="stmt-head"><h3>Invoices and receipts</h3><button type="button" className="btn-small" onClick={() => setScansOpen(true)}>Add invoices and receipts</button></div>
        <div className="note">Scans saved by Image Capture in Scan-Inbox appear by themselves; you can also choose PDFs here. Each is read on this Mac, shown as a preview, and filed as a new file in Expenses or Income only after you approve it.</div></section>
      {err && <p className="muted">Could not load projects.</p>}
      {data && (
        <>
          {data.gaps.length > 0 && (
            <div className="notice"><span>Missing in the project register: {data.gaps.map((g) => g.code).join(", ")}. Open a project for details.</span></div>
          )}
          <h3 className="serif">Projects</h3>
          <div className="proj-grid">{data.projects.map((p) => <Card key={p.code} p={p} onOpen={() => setOpen(p.code)} />)}</div>
          <h3 className="serif">Threads</h3>
          <div className="proj-grid">{data.threads.map((p) => <Card key={p.code} p={p} onOpen={() => setOpen(p.code)} />)}</div>
        </>
      )}
      {open && <ProjectDrawer code={open} onClose={() => setOpen(null)} />}
      {scansOpen && <ScansDrawer onClose={() => { setScansOpen(false); sc.reload(); }} onChanged={() => { a.reload(); sc.reload(); }} />}
      {hoursOpen && <HoursDrawer onClose={() => setHoursOpen(false)} />}
      {audit && <AuditDrawer initial={null} onClose={() => setAudit(false)} onChanged={a.reload} />}
    </main>
  );
}
