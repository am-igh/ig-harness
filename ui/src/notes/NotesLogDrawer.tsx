import { useCallback, useEffect, useState } from "react";
import { type Note, getNotesLog } from "../api";
import { dayHeading, doneDay } from "../format";
import { Shell } from "../today/Drawer";
import { NoteRow } from "./NotesList";

const RANGES: [string, number][] = [["30 days", 30], ["90 days", 90], ["All time", 0]];

/** Every note and follow-up, newest first: the record. */
export default function NotesLogDrawer({ today, onClose, onChanged }: { today: string; onClose: () => void; onChanged: () => void }) {
  const [days, setDays] = useState(30);
  const [q, setQ] = useState("");
  const [items, setItems] = useState<Note[] | null>(null);
  const load = useCallback(() => getNotesLog(days, q).then((r) => setItems(r.items)), [days, q]);
  useEffect(() => { const t = setTimeout(load, q ? 250 : 0); return () => clearTimeout(t); }, [load, q]);
  const changed = () => { load(); onChanged(); };
  const groups: [string, Note[]][] = [];
  for (const n of items ?? []) {
    const d = doneDay(n.created_at);
    if (groups.length && groups[groups.length - 1][0] === d) groups[groups.length - 1][1].push(n); else groups.push([d, [n]]);
  }
  const n = items?.length ?? 0;
  return (
    <Shell kicker="NOTES" title={items ? `${n} note${n === 1 ? "" : "s"}` : "Loading…"} meta="Everything you have written down, with when. Follow-ups show what became of them." onClose={onClose}>
      <div className="range" role="group" aria-label="Period">
        {RANGES.map(([label, d]) => <button key={d} type="button" className={d === days ? "on" : ""} aria-pressed={d === days} onClick={() => setDays(d)}>{label}</button>)}
      </div>
      <input className="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search your notes…" aria-label="Search notes" />
      {items && n === 0 && <p className="muted">{q ? "Nothing matches." : "No notes yet. Use “＋ Add a note or follow-up” on Today & overdue or on an email."}</p>}
      {groups.map(([day, rows]) => (
        <div key={day} className="done-group">
          <div className="kicker">{dayHeading(day, today).toUpperCase()}</div>
          {rows.map((r) => <NoteRow key={r.id} n={r} onChanged={changed} showParent />)}
        </div>
      ))}
    </Shell>
  );
}
