import { useEffect, useRef, useState } from "react";
import { type CaptureProposal, type ResearchJob, askChat, confirmCapture, clearResearch, getLibrary, getResearch, getResearchAgent, saveResearch, startResearch } from "../api";
import { dayShort } from "../format";

type Research = { id?: string; query: string; job?: ResearchJob; confirm?: string[]; blocked?: string[]; error?: string };
type Turn = { id: number; me: string; mode: "harness" | "research"; text?: string; kind?: string; proposal?: CaptureProposal; done?: string; err?: string; research?: Research };

const host = (u: string) => { try { return new URL(u).hostname.replace(/^www\./, ""); } catch { return u; } };

/** The chat box under "Emails needing you". Two modes, always visible:
 *  - Ask the harness: the local model answers from the harness's own data; "remind me to …" becomes a to-do you confirm.
 *  - Research the web: your own words go to a search engine on this Mac, a few public pages are read, and the local model summarises them with sources. No harness data is involved.
 *  Nothing is kept after the page closes. */
export default function ChatBox({ onChanged, onOpenLibrary }: { onChanged: () => void; onOpenLibrary: () => void }) {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [text, setText] = useState("");
  const [mode, setMode] = useState<"harness" | "research">("harness");
  const [busy, setBusy] = useState(false);
  const next = useRef(1);
  const [saved, setSaved] = useState<number | null>(null);
  const loadSaved = () => getLibrary().then((d) => setSaved(d.total)).catch(() => setSaved(null));
  useEffect(() => { loadSaved(); }, []);
  const patch = (id: number, p: Partial<Turn>) => setTurns((t) => t.map((x) => (x.id === id ? { ...x, ...p } : x)));
  const patchResearch = (id: number, p: Partial<Research>) => setTurns((t) => t.map((x) => (x.id === id && x.research ? { ...x, research: { ...x.research, ...p } } : x)));

  const runResearch = async (id: number, query: string, confirm: boolean) => {
    setBusy(true);
    try {
      if (!(await getResearchAgent()).alive) { patchResearch(id, { error: "The research helper is not running. In Terminal, in the ig-harness folder: make research-install" }); return; }
      const r = await startResearch(query, confirm);
      if (r.state === "blocked") { patchResearch(id, { blocked: r.reasons }); return; }
      if (r.state === "needs_confirm") { patchResearch(id, { confirm: r.reasons }); return; }
      patchResearch(id, { confirm: undefined, id: r.id });
      for (let i = 0; i < 120; i++) {
        const j = await getResearch(r.id);
        patchResearch(id, { job: j });
        if (j.state === "done" || j.state === "failed") return;
        await new Promise((res) => setTimeout(res, 1500));
      }
      patchResearch(id, { error: "This is taking too long. Try again." });
    } catch (e) { patchResearch(id, { error: (e as Error).message }); }
    finally { setBusy(false); }
  };

  const clearTurn = (t: Turn) => { if (t.research?.id) clearResearch(t.research.id).catch(() => {}); setTurns((x) => x.filter((y) => y.id !== t.id)); };
  const clearAll = () => { clearResearch().catch(() => {}); setTurns([]); };

  const submit = async () => {
    const message = text.trim();
    if (!message || busy) return;
    const id = next.current++;
    setText("");
    if (mode === "research") {
      setTurns((t) => [...t.slice(-5), { id, me: message, mode, research: { query: message } }]);
      return runResearch(id, message, false);
    }
    setBusy(true);
    setTurns((t) => [...t.slice(-5), { id, me: message, mode }]);
    try {
      const r = await askChat(message);
      patch(id, r.kind === "capture" ? { kind: "capture", proposal: r.proposal } : { kind: r.kind, text: r.text });
    } catch (e) { patch(id, { kind: "unavailable", text: (e as Error).message }); }
    finally { setBusy(false); }
  };

  const research = mode === "research";
  return (
    <div className={`chat ${research ? "chat-research" : ""}`} role="group" aria-label="Harness chat">
      {turns.length > 0 && (
        <div className="chat-log" aria-live="polite">
          <button type="button" className="btn-ghost chat-clear-all" onClick={clearAll} disabled={busy}>Clear chat</button>
          {turns.map((t) => (
            <div key={t.id} className="chat-turn">
              <div className="chat-me">{t.mode === "research" && <span className="chat-tag">web</span>}{t.me}<button type="button" className="chat-x" onClick={() => clearTurn(t)} aria-label="Clear this message and its answer" title="Clear this one">✕</button></div>
              {t.research ? <ResearchView r={t.research} onSaved={loadSaved} onConfirm={() => runResearch(t.id, t.research!.query, true)} onCancel={() => patchResearch(t.id, { confirm: undefined, error: "Cancelled. Nothing was searched." })} /> : <>
                {t.kind === undefined && <div className="chat-bot muted">Thinking…</div>}
                {t.text && <div className={`chat-bot ${t.kind === "unavailable" ? "warn" : ""}`}>{t.text}</div>}
                {t.proposal && !t.done && <Proposal p={t.proposal} onCancel={() => patch(t.id, { done: "Cancelled." })}
                  onConfirm={async (p) => { try { const r = await confirmCapture(p); patch(t.id, { done: `Added to Today, due ${dayShort(r.due)}.` }); onChanged(); } catch (e) { patch(t.id, { err: (e as Error).message }); } }} err={t.err} />}
                {t.done && <div className="chat-bot">{t.done}</div>}
              </>}
            </div>
          ))}
        </div>
      )}
      <div className="chat-modes" role="group" aria-label="Chat mode">
        <button type="button" aria-pressed={!research} className={!research ? "on" : ""} onClick={() => setMode("harness")}>Ask the harness</button>
        <button type="button" aria-pressed={research} className={research ? "on" : ""} onClick={() => setMode("research")}>Research the web</button>
      </div>
      <button type="button" className="btn-ghost chat-lib" onClick={onOpenLibrary}>Saved research{saved ? ` (${saved})` : ""}</button>
      {research && <div className="muted small chat-hint">Your words go to a search engine on this Mac and a few public pages are read. Nothing from your emails or records is used. Confidential-looking details are stopped or confirmed first.</div>}
      <form className="chatbar" onSubmit={(e) => { e.preventDefault(); submit(); }}>
        <input type="text" value={text} onChange={(e) => setText(e.target.value)} maxLength={research ? 300 : 600} aria-label={research ? "Search the web" : "Ask the harness or add a to-do"}
          placeholder={research ? "What do you want to look up?" : "Ask about your data, or “remind me to …”"} />
        <button type="submit" disabled={busy || !text.trim()}>{busy ? "…" : research ? "Search" : "Ask"}</button>
      </form>
    </div>
  );
}

function ResearchView({ r, onConfirm, onCancel, onSaved }: { r: Research; onConfirm: () => void; onCancel: () => void; onSaved: () => void }) {
  const [copied, setCopied] = useState(false);
  const [state, setState] = useState<"idle" | "saved" | string>("idle");
  useEffect(() => { if (copied) { const t = setTimeout(() => setCopied(false), 1500); return () => clearTimeout(t); } }, [copied]);
  if (r.blocked) return <div className="chat-bot warn">Not searched: {r.blocked.join(" ")} Rephrase it without that detail.</div>;
  if (r.confirm) return (
    <div className="chat-bot chat-proposal">
      <div>This will be searched on the web:</div>
      <div className="mono small">{r.query}</div>
      <ul className="small">{r.confirm.map((x) => <li key={x}>{x}</li>)}</ul>
      <div className="chat-prop-row">
        <button type="button" className="btn-primary" onClick={onConfirm}>Search anyway</button>
        <button type="button" className="btn-ghost" onClick={onCancel}>Cancel</button>
      </div>
    </div>
  );
  if (r.error && !r.job) return <div className="chat-bot warn">{r.error}</div>;
  const j = r.job;
  if (!j || j.state === "searching") return <div className="chat-bot muted">Searching and reading pages… (about a minute)</div>;
  if (j.state === "summarising") return <div className="chat-bot muted">Read {j.sources.length} page{j.sources.length === 1 ? "" : "s"}. Summarising on your Mac…</div>;
  if (j.state === "failed") return <div className="chat-bot warn">{j.error ?? "The search failed."}</div>;
  return (
    <div className="chat-bot">
      {j.answer ? <div>{j.answer}</div> : null}
      {j.error && <div className="muted small">{j.error}</div>}
      {j.sources.length > 0 && (
        <ol className="chat-sources">
          {j.sources.map((s) => <li key={s.n}><a href={s.url} target="_blank" rel="noopener noreferrer">{s.title || host(s.url)}</a> <span className="muted">· {host(s.url)}</span></li>)}
        </ol>
      )}
      <div className="muted small">From the web, summarised by your local model: check the sources before relying on it. Searched for: {j.query}</div>
      {j.answer && r.id && <button type="button" className="btn-ghost" disabled={state === "saved"} onClick={async () => { try { await saveResearch(r.id!); setState("saved"); onSaved(); } catch (e) { setState((e as Error).message); } }}>{state === "saved" ? "Saved to library" : "Save to library"}</button>}
      {state !== "idle" && state !== "saved" && <div className="edit-err">{state}</div>}
      {j.answer && <button type="button" className="btn-ghost" onClick={() => { navigator.clipboard?.writeText(`${j.answer}\n\n${j.sources.map((s) => `[${s.n}] ${s.title} ${s.url}`).join("\n")}`).then(() => setCopied(true)).catch(() => {}); }}>{copied ? "Copied" : "Copy answer"}</button>}
    </div>
  );
}

function Proposal({ p, onConfirm, onCancel, err }: { p: CaptureProposal; onConfirm: (p: CaptureProposal) => void; onCancel: () => void; err?: string }) {
  const [v, setV] = useState(p);
  return (
    <div className="chat-bot chat-proposal">
      <div className="muted small">Add this to Today?</div>
      <input value={v.text} onChange={(e) => setV({ ...v, text: e.target.value })} aria-label="To-do" />
      <div className="chat-prop-row">
        <input type="date" value={v.due_date ?? ""} onChange={(e) => setV({ ...v, due_date: e.target.value || null })} aria-label="Due date" />
        {v.space === "work" && <input className="phone-code" value={v.project_code ?? ""} placeholder="project" maxLength={8} onChange={(e) => setV({ ...v, project_code: e.target.value.toUpperCase() || null })} aria-label="Project code" />}
        <label className="phone-personal"><input type="checkbox" checked={v.space === "personal"} onChange={(e) => setV({ ...v, space: e.target.checked ? "personal" : "work", project_code: e.target.checked ? null : v.project_code })} /> Personal</label>
      </div>
      {err && <div className="edit-err">{err}</div>}
      <div className="chat-prop-row">
        <button type="button" className="btn-primary" onClick={() => onConfirm(v)} disabled={!v.text.trim()}>Add to Today</button>
        <button type="button" className="btn-ghost" onClick={onCancel}>Cancel</button>
      </div>
    </div>
  );
}
