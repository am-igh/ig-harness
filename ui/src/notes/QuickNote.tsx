import { useState } from "react";
import NoteForm from "./NoteForm";

/** A free-standing note or follow-up, from the top of a panel. */
export default function QuickNote({ onAdded, onOpenLog, placeholder }: { onAdded: () => void; onOpenLog: () => void; placeholder: string }) {
  const [open, setOpen] = useState(false);
  const [saved, setSaved] = useState(false);
  return (
    <div className="quick-note">
      {open ? (
        <>
          <NoteForm onAdded={() => { onAdded(); setOpen(false); setSaved(true); setTimeout(() => setSaved(false), 3000); }} placeholder={placeholder} />
          <button type="button" className="link-quiet" onClick={() => setOpen(false)}>cancel</button>
        </>
      ) : (
        <div className="quick-row">
          <button type="button" className="link-quiet" onClick={() => setOpen(true)}>＋ Add a note or follow-up</button>
          <button type="button" className="link-quiet" onClick={onOpenLog}>All notes →</button>
          {saved && <span className="note-hint">Saved ✓</span>}
        </div>
      )}
    </div>
  );
}
