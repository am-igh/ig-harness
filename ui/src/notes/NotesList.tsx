import { useState } from "react";
import { type Note, deleteNote, revealNote } from "../api";
import { dayShort, doneDay, doneTime } from "../format";

function FollowUp({ n }: { n: Note }) {
  const f = n.follow_up;
  if (!f) return null;
  if (f.status === "done") return <span className="fu done">✓ follow-up done{f.done_at ? ` ${dayShort(doneDay(f.done_at))} ${doneTime(f.done_at)}` : ""}</span>;
  if (f.status === "dropped") return <span className="fu">follow-up removed</span>;
  return <span className="fu open">→ in Today &amp; overdue{f.due ? ` · due ${dayShort(f.due)}` : ""}</span>;
}

export function NoteRow({ n, onChanged, showParent = false }: { n: Note; onChanged: () => void; showParent?: boolean }) {
  const [shown, setShown] = useState<string | null>(null);
  const reveal = async () => { setShown((await revealNote(n.id)).text); setTimeout(() => setShown(null), 60_000); };
  return (
    <div className={`note-row-item ${n.kind === "followup" ? "fu-note" : ""}`}>
      <div className="note-meta">
        <span className="mono">{dayShort(doneDay(n.created_at))} {doneTime(n.created_at)}</span>
        {n.kind === "followup" && <span className="chip chip-personal">follow-up</span>}
        {showParent && n.parent && <span className="muted small">on {n.parent.masked ? "🔒 " : ""}{n.parent.title}</span>}
        <FollowUp n={n} />
        <button type="button" className="link-quiet inline" onClick={async () => { await deleteNote(n.id); onChanged(); }} title="Remove this note" aria-label="Remove note">remove</button>
      </div>
      {n.masked && shown === null
        ? <button type="button" className="masked-title" onClick={reveal}>🔒 {n.text} <span>show details</span></button>
        : <div className="note-text">{shown ?? n.text}{shown !== null && <button type="button" className="link-quiet inline" onClick={() => setShown(null)}>hide</button>}</div>}
    </div>
  );
}
