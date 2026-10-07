import { useRef, useState } from "react";
import { type CaptureProposal, askChat, confirmCapture } from "../api";
import { dayShort } from "../format";

type Turn = { id: number; me: string; text?: string; kind?: string; proposal?: CaptureProposal; done?: string; err?: string };

/** The chat box under "Emails needing you". Questions are answered by the local model from the harness's own data; a message starting "remind me to …" becomes a to-do you confirm. Nothing is kept after the page closes. */
export default function ChatBox({ onChanged }: { onChanged: () => void }) {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const next = useRef(1);
  const patch = (id: number, p: Partial<Turn>) => setTurns((t) => t.map((x) => (x.id === id ? { ...x, ...p } : x)));

  const submit = async () => {
    const message = text.trim();
    if (!message || busy) return;
    const id = next.current++;
    setText(""); setBusy(true);
    setTurns((t) => [...t.slice(-5), { id, me: message }]);
    try {
      const r = await askChat(message);
      patch(id, r.kind === "capture" ? { kind: "capture", proposal: r.proposal } : { kind: r.kind, text: r.text });
    } catch (e) { patch(id, { kind: "unavailable", text: (e as Error).message }); }
    finally { setBusy(false); }
  };

  return (
    <div className="chat" role="group" aria-label="Harness chat">
      {turns.length > 0 && (
        <div className="chat-log" aria-live="polite">
          {turns.map((t) => (
            <div key={t.id} className="chat-turn">
              <div className="chat-me">{t.me}</div>
              {t.kind === undefined && <div className="chat-bot muted">Thinking…</div>}
              {t.text && <div className={`chat-bot ${t.kind === "unavailable" ? "warn" : ""}`}>{t.text}</div>}
              {t.proposal && !t.done && <Proposal p={t.proposal} onCancel={() => patch(t.id, { done: "Cancelled." })}
                onConfirm={async (p) => { try { const r = await confirmCapture(p); patch(t.id, { done: `Added to Today, due ${dayShort(r.due)}.` }); onChanged(); } catch (e) { patch(t.id, { err: (e as Error).message }); } }} err={t.err} />}
              {t.done && <div className="chat-bot">{t.done}</div>}
            </div>
          ))}
        </div>
      )}
      <form className="chatbar" onSubmit={(e) => { e.preventDefault(); submit(); }}>
        <input type="text" value={text} onChange={(e) => setText(e.target.value)} maxLength={600} aria-label="Ask the harness or add a to-do"
          placeholder="Ask about your data, or “remind me to …”" />
        <button type="submit" disabled={busy || !text.trim()}>{busy ? "…" : "Ask"}</button>
      </form>
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
