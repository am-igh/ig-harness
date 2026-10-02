import { useCallback, useEffect, useState } from "react";
import { type WatchName, addWatch, deleteWatch, getWatch, redoTriage } from "../api";

/** Names that always put an email in front of her when they are on the thread (sender, To, Cc, earlier senders, or written in the text). No model involved. */
export default function WatchList() {
  const [items, setItems] = useState<WatchName[]>([]);
  const [text, setText] = useState("");
  const [note, setNote] = useState("");
  const load = useCallback(() => getWatch().then((r) => setItems(r.items)), []);
  useEffect(() => { load(); }, [load]);
  const add = async () => {
    if (text.trim().length < 3) return;
    await addWatch(text.trim()); setText(""); await redoTriage(); setNote("Saved. Emails are being re-checked now."); load();
  };
  return (
    <section className="card-box" aria-label="Always show me">
      <h3>Always show me</h3>
      <div className="note">People whose emails you never want to miss. If the name is on a thread (sender, To, Cc, earlier message, or written in the text), it is shown as needing you. Use the full name, e.g. “Felix Staehli”.</div>
      {items.map((w) => (
        <div key={w.id} className="rule"><span>{w.name}</span>
          <button type="button" aria-label={`Remove ${w.name}`} onClick={async () => { await deleteWatch(w.id); await redoTriage(); load(); }}>✕</button></div>
      ))}
      <div className="add-row">
        <input value={text} onChange={(e) => setText(e.target.value)} placeholder="Add a name…" maxLength={80} onKeyDown={(e) => e.key === "Enter" && add()} aria-label="New name" />
        <button type="button" className="btn-small" onClick={add} disabled={text.trim().length < 3}>Add</button>
      </div>
      {note && <div className="note">{note}</div>}
    </section>
  );
}
