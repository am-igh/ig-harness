import { useCallback, useEffect, useState } from "react";
import { type SavedResearch, deleteSaved, getLibrary, setLibraryProject } from "../api";
import { dayShort } from "../format";
import { Shell } from "./Drawer";

const host = (u: string) => { try { return new URL(u).hostname.replace(/^www\./, ""); } catch { return u; } };

function Entry({ r, onChanged }: { r: SavedResearch; onChanged: () => void }) {
  const [code, setCode] = useState(r.project_code ?? "");
  const [err, setErr] = useState("");
  const [open, setOpen] = useState(false);
  const [copied, setCopied] = useState(false);
  const saveCode = async () => { setErr(""); try { await setLibraryProject(r.id, code.trim() || null); onChanged(); } catch (e) { setErr((e as Error).message); } };
  return (
    <div className="lib-entry">
      <button type="button" className="lib-head" onClick={() => setOpen(!open)} aria-expanded={open}>
        <span className="lib-q">{r.query}</span>
        <span className="muted small">{dayShort(r.saved_at.slice(0, 10))}{r.project_code ? ` · ${r.project_code}` : ""}</span>
      </button>
      {open && (
        <div className="lib-body">
          <div className="lib-answer">{r.answer}</div>
          <ol className="chat-sources">
            {r.sources.map((s) => <li key={s.n}><a href={s.url} target="_blank" rel="noopener noreferrer">{s.title || host(s.url)}</a> <span className="muted">· {host(s.url)} · read {s.fetched_at.slice(0, 10)}</span></li>)}
          </ol>
          <div className="muted small">From the web, summarised by {r.model ?? "a local model"}: check the sources before relying on it.</div>
          <div className="chat-prop-row">
            <input className="phone-code" value={code} placeholder="project" maxLength={8} onChange={(e) => setCode(e.target.value.toUpperCase())} aria-label="Project code" />
            <button type="button" className="btn-ghost" onClick={saveCode} disabled={code === (r.project_code ?? "")}>Set project</button>
            <button type="button" className="btn-ghost" onClick={() => navigator.clipboard?.writeText(`${r.query}\n\n${r.answer}\n\n${r.sources.map((s) => `[${s.n}] ${s.title} ${s.url}`).join("\n")}`).then(() => { setCopied(true); setTimeout(() => setCopied(false), 1500); }).catch(() => {})}>{copied ? "Copied" : "Copy"}</button>
            <button type="button" className="btn-ghost" onClick={async () => { await deleteSaved(r.id); onChanged(); }}>Delete</button>
          </div>
          {err && <div className="edit-err">{err}</div>}
        </div>
      )}
    </div>
  );
}

/** The research library: answers she chose to keep (summary, question, source links), searchable. They stay on this Mac and are not used by "Ask the harness". */
export default function ResearchLibraryDrawer({ onClose }: { onClose: () => void }) {
  const [q, setQ] = useState("");
  const [d, setD] = useState<{ items: SavedResearch[]; total: number } | null>(null);
  const load = useCallback(() => getLibrary(q).then(setD).catch(() => setD(null)), [q]);
  useEffect(() => { const t = setTimeout(load, 200); return () => clearTimeout(t); }, [load]);
  return (
    <Shell kicker="SAVED RESEARCH" title="Research library" meta={d ? `${d.total} saved answer${d.total === 1 ? "" : "s"}, kept on this Mac` : "Loading…"} onClose={onClose} wide>
      <input className="lib-search" type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search your saved research…" aria-label="Search saved research" />
      {d && d.items.length === 0 && <p className="muted">{d.total === 0 ? "Nothing saved yet. Under a research answer, click “Save to library”." : "Nothing matches."}</p>}
      {d?.items.map((r) => <Entry key={r.id} r={r} onChanged={load} />)}
    </Shell>
  );
}
