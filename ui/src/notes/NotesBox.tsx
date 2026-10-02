import { useCallback, useEffect, useState } from "react";
import { type Note, getNotes } from "../api";
import NoteForm from "./NoteForm";
import { NoteRow } from "./NotesList";

/** The notes on one item or email: what was written, and a form to add more. */
export default function NotesBox({ parent, onChanged }: { parent: { type: string; id: number }; onChanged?: () => void }) {
  const [items, setItems] = useState<Note[] | null>(null);
  const load = useCallback(() => getNotes(parent.type, parent.id).then((r) => setItems(r.items)).catch(() => setItems([])), [parent.type, parent.id]);
  useEffect(() => { load(); }, [load]);
  const changed = () => { load(); onChanged?.(); };
  return (
    <div className="notes-box">
      {(items ?? []).map((n) => <NoteRow key={n.id} n={n} onChanged={changed} />)}
      {items && items.length === 0 && <div className="note-hint">No notes yet. Add context, or a follow-up that goes into Today &amp; overdue.</div>}
      <NoteForm parent={parent} onAdded={changed} compact />
    </div>
  );
}
