import { useState } from "react";
import { addNote } from "../api";

/** Write a note (context) or a follow-up (which also becomes a task in Today & overdue). */
export default function NoteForm({ parent, onAdded, placeholder = "Add a note…", compact = false }: {
  parent?: { type: string; id: number }; onAdded: () => void; placeholder?: string; compact?: boolean;
}) {
  const [text, setText] = useState("");
  const [kind, setKind] = useState<"note" | "followup">("note");
  const [due, setDue] = useState("");
  const [personal, setPersonal] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  const submit = async () => {
    if (!text.trim() || busy) return;
    setBusy(true); setErr("");
    try {
      await addNote({ text, kind, parent_type: parent?.type ?? null, parent_id: parent?.id ?? null, due: kind === "followup" && due ? due : null, personal });
      setText(""); setDue(""); setPersonal(false); onAdded();
    } catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
  };

  return (
    <div className={`note-form ${compact ? "compact" : ""}`}>
      <textarea rows={compact ? 2 : 3} value={text} maxLength={2000} placeholder={placeholder} aria-label="Note text"
        onChange={(e) => setText(e.target.value)} onKeyDown={(e) => { if ((e.metaKey || e.ctrlKey) && e.key === "Enter") submit(); }} />
      <div className="note-row">
        <div className="range" role="group" aria-label="Kind">
          <button type="button" className={kind === "note" ? "on" : ""} aria-pressed={kind === "note"} onClick={() => setKind("note")}>Note</button>
          <button type="button" className={kind === "followup" ? "on" : ""} aria-pressed={kind === "followup"} onClick={() => setKind("followup")}>Follow-up</button>
        </div>
        {kind === "followup" && <label className="note-due">due <input type="date" value={due} onChange={(e) => setDue(e.target.value)} title="Leave empty for today" /></label>}
        {!parent && <label className="note-due"><input type="checkbox" checked={personal} onChange={(e) => setPersonal(e.target.checked)} /> personal</label>}
        <button type="button" className="btn-small" onClick={submit} disabled={busy || !text.trim()}>{kind === "followup" ? "Add follow-up" : "Add note"}</button>
      </div>
      {kind === "followup" && <div className="note-hint">A follow-up also appears in Today &amp; overdue{due ? "" : " today"} so you don't forget it.</div>}
      {err && <div className="edit-err">{err}</div>}
    </div>
  );
}
