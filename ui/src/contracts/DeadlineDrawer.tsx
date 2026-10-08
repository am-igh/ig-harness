import { useCallback, useEffect, useState } from "react";
import { type PMDoc, type PMWorkspace, attachPMDoc, getPMVersions, getPMWorkspace, makePMTemplate, savePMVersion, setPMDeadlineStatus, startPMDraft } from "../api";
import { Shell } from "../today/Drawer";
import { dayShort } from "../format";
import { STATUS_LABEL, dateY } from "./fmt";

const ICON: Record<string, string> = { funder_form: "📄", template: "🧩", draft: "✏️", submitted: "✅", other: "📎" };

function Viewer({ doc, onChanged, onClose }: { doc: PMDoc; onChanged: () => void; onClose: () => void }) {
  const [text, setText] = useState(doc.content ?? "");
  const [versions, setVersions] = useState<PMDoc[]>([]);
  const [shown, setShown] = useState<PMDoc>(doc);
  const [err, setErr] = useState(""); const [saved, setSaved] = useState(false); const [copied, setCopied] = useState(false);
  useEffect(() => { setShown(doc); setText(doc.content ?? ""); setSaved(false); getPMVersions(doc.id).then(setVersions).catch(() => setVersions([])); }, [doc]);
  const newest = versions[0]?.version ?? doc.version;
  const editable = doc.kind === "draft" && shown.version === newest;
  const save = async () => { setErr(""); try { await savePMVersion(shown.id, text); setSaved(true); onChanged(); } catch (e) { setErr((e as Error).message); } };
  return (
    <div className="dl-viewer">
      <div className="dl-viewer-head"><b>{shown.title}</b><span className="muted small">version {shown.version} of {versions.length || 1} · {shown.author === "rules" ? "made by rules" : "by you"} · {dateY(shown.created_at.slice(0, 10))}</span>
        <button type="button" className="btn-ghost" onClick={onClose}>Close</button></div>
      {versions.length > 1 && <label className="small muted">Version <select value={shown.id} onChange={(e) => { const v = versions.find((x) => x.id === Number(e.target.value))!; setShown(v); setText(v.content ?? ""); }}>
        {versions.map((v) => <option key={v.id} value={v.id}>{v.version} · {dateY(v.created_at.slice(0, 10))}{v.version === newest ? " (newest)" : ""}</option>)}</select></label>}
      {editable ? <textarea className="dl-text" value={text} onChange={(e) => { setText(e.target.value); setSaved(false); }} rows={22} aria-label="Draft text" /> : <pre className="dl-text dl-pre">{text}</pre>}
      {err && <div className="edit-err">{err}</div>}
      <div className="chat-prop-row">
        {editable && <button type="button" className="btn-primary" onClick={save} disabled={saved || !text.trim()}>{saved ? "Saved as a new version" : "Save as a new version"}</button>}
        <a className="btn-ghost link-btn" href={`/api/pm/documents/${shown.id}/download`}>Download (.md)</a>
        <button type="button" className="btn-ghost" onClick={() => navigator.clipboard?.writeText(text).then(() => { setCopied(true); setTimeout(() => setCopied(false), 1500); }).catch(() => {})}>{copied ? "Copied" : "Copy text"}</button>
      </div>
      {!editable && doc.kind === "draft" && <div className="small muted">This is an older version: nothing is overwritten. Select the newest version to edit.</div>}
    </div>
  );
}

/** What sits behind one reporting deadline: what the funder requires, the funder's form, a template made from the requirements, the working draft and the submitted copy. */
export default function DeadlineDrawer({ id, onClose, onChanged }: { id: number; onClose: () => void; onChanged: () => void }) {
  const [w, setW] = useState<PMWorkspace | null>(null);
  const [open, setOpen] = useState<PMDoc | null>(null);
  const [err, setErr] = useState(""); const [busy, setBusy] = useState(false);
  const [kind, setKind] = useState("funder_form"); const [title, setTitle] = useState(""); const [path, setPath] = useState(""); const [note, setNote] = useState(""); const [showAttach, setShowAttach] = useState(false);
  const load = useCallback((keep?: number) => getPMWorkspace(id).then((x) => { setW(x); if (keep != null) setOpen(x.documents.find((d) => d.id === keep) ?? null); else setOpen((o) => (o ? x.documents.find((d) => d.kind === o.kind && d.title === o.title) ?? null : null)); }).catch(() => setW(null)), [id]);
  useEffect(() => { load(); }, [load]);
  if (!w) return <Shell kicker="REPORT" title="Loading…" meta="" onClose={onClose}><p className="muted">Loading…</p></Shell>;
  const d = w.deadline, r = w.requirement;
  const run = async (fn: () => Promise<PMDoc | { id: number }>) => { setErr(""); setBusy(true); try { const x = await fn(); await load("kind" in x ? x.id : undefined); onChanged(); } catch (e) { setErr((e as Error).message); } finally { setBusy(false); } };
  const hasDraft = w.documents.some((x) => x.kind === "draft");
  return (
    <Shell kicker={`REPORT · ${d.funder}`} title={d.title} meta={`${d.project} · due ${dateY(d.due_date)}${d.period.match(/^[A-Z]/) && !["fixed date", "final", "start"].includes(d.period) ? ` · ${d.period}` : ""}`} onClose={onClose} wide>
      <div className="dl-status"><span className={d.days_left < 0 && (d.status === "todo" || d.status === "drafting") ? "bad" : "muted"}>{d.status === "todo" || d.status === "drafting" ? (d.days_left < 0 ? `${-d.days_left} days overdue` : d.days_left === 0 ? "due today" : `due in ${d.days_left} days`) : d.submitted_on ? `done ${dayShort(d.submitted_on)}` : ""}</span>
        <select value={d.status} onChange={async (e) => { await setPMDeadlineStatus(d.id, e.target.value); await load(); onChanged(); }} aria-label="Status" className={`pm-status s-${d.status}`}>
          {Object.entries(STATUS_LABEL).map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select></div>
      <div className="related"><div className="kicker">WHAT {d.funder.toUpperCase()} REQUIRES</div>
        <div className="facts"><span>Requirement</span><span>{r.canon_label}{r.clause ? ` · ${r.clause}` : ""}</span><span>Timing</span><span>{r.rule}</span><span>Language</span><span>{r.language ?? "not specified"}</span>
          <span>Format</span><span>{r.format ?? "free form"}</span><span>Detail</span><span>{r.detail ?? "not specified"}</span>{r.note && <><span>Note</span><span>{r.note}</span></>}
          <span>Contract</span><span>{d.contract}</span>{d.contact && <><span>Contact</span><span>{d.contact}</span></>}</div>
        {w.rules.length > 0 && <div className="small muted">Rules of this contract to respect: {w.rules.map((x) => x.title).join(" · ")}</div>}</div>
      <div className="related"><div className="kicker">DOCUMENTS</div>
        {w.documents.length === 0 && <p className="muted">Nothing here yet. Create a template from the requirements, or attach the funder's form (it stays in your folders; the harness only remembers where).</p>}
        {w.documents.map((x) => (
          <div key={x.id} className={`dl-doc ${open?.id === x.id ? "on" : ""}`}>
            <span className="dl-icon">{ICON[x.kind]}</span>
            <div className="dl-doc-main"><b>{x.title}</b><div className="small muted">{x.kind_label}{x.content != null ? ` · version ${x.version}${(x.versions ?? 1) > 1 ? ` of ${x.versions}` : ""}` : ""}{x.note ? ` · ${x.note}` : ""}</div>
              {x.file_path && <div className="small mono">{x.file_path}</div>}</div>
            {x.content != null ? <button type="button" className="btn-ghost" onClick={() => setOpen(open?.id === x.id ? null : x)}>{open?.id === x.id ? "Hide" : "Open"}</button>
              : <button type="button" className="btn-ghost" onClick={() => navigator.clipboard?.writeText(x.file_path ?? "").catch(() => {})}>Copy path</button>}
          </div>))}
        <div className="chat-prop-row">
          <button type="button" className="btn-primary" disabled={busy} onClick={() => run(() => makePMTemplate(id))}>{w.has_template ? "Make the template again" : "Create a template from the requirements"}</button>
          {w.has_template && !hasDraft && <button type="button" className="btn-primary" disabled={busy} onClick={() => run(() => startPMDraft(id))}>Start a draft from the template</button>}
          <button type="button" className="btn-ghost" onClick={() => setShowAttach(!showAttach)}>Attach a form or a copy</button>
        </div>
        {showAttach && (
          <form className="pm-form" onSubmit={(e) => { e.preventDefault(); run(() => attachPMDoc(id, { kind, title, file_path: path, note: note || undefined })).then(() => { setShowAttach(false); setTitle(""); setPath(""); setNote(""); }); }}>
            <div className="pm-form-row"><select value={kind} onChange={(e) => setKind(e.target.value)} aria-label="Kind"><option value="funder_form">Funder's form</option><option value="submitted">Submitted copy</option><option value="other">Other</option></select>
              <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Title" aria-label="Title" required /></div>
            <div className="pm-form-row"><input value={path} onChange={(e) => setPath(e.target.value)} placeholder="Where it is kept (path in your folders)" aria-label="Location" required />
              <input value={note} onChange={(e) => setNote(e.target.value)} placeholder="Note (optional)" aria-label="Note" /></div>
            <button type="submit" className="btn-primary" disabled={busy}>Attach</button>
          </form>)}
        {err && <div className="edit-err">{err}</div>}
      </div>
      {open && open.content != null && <Viewer doc={open} onChanged={() => load(open.id)} onClose={() => setOpen(null)} />}
    </Shell>
  );
}
