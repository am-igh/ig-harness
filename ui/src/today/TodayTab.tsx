import { useCallback, useEffect, useRef, useState } from "react";
import { type Item, type Today, editItem, getToday, setDone } from "../api";
import { dayShort, doneTime, dueLabel, timeOf } from "../format";
import EmailList from "../email/EmailList";
import Drawer, { type Panel } from "./Drawer";
import { useReveal } from "./useReveal";
import NotesBox from "../notes/NotesBox";
import QuickNote from "../notes/QuickNote";
import AuditTile, { useAuditStatus } from "../finance/AuditTile";
import Lake from "./Lake";

const WIDGETS = [
  { title: "Hours this week", sub: "Friday pass fills the gaps", phase: "Phase 4" },
  { title: "Budget burn", sub: "Highest open mandate", phase: "Phase 4" },
  { title: "Scan inbox", sub: "Filed automatically", phase: "Phase 4" },
];

function Editor({ it, onClose, onSaved }: { it: Item; onClose: () => void; onSaved: () => void }) {
  const [title, setTitle] = useState(it.title);
  const [due, setDue] = useState(it.due ?? "");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const isWaiting = it.type === "waiting_on", canClear = it.type !== "deadline";
  const save = async () => {
    const patch: { title?: string; due?: string | null } = {};
    if (title.trim() !== it.title) patch.title = title;
    if ((due || null) !== it.due) patch.due = due || null;
    if (Object.keys(patch).length === 0) return onClose();
    setBusy(true); setErr("");
    try { await editItem(it, patch); onSaved(); onClose(); } catch (e) { setErr((e as Error).message); setBusy(false); }
  };
  const reset = async () => { setBusy(true); try { await editItem(it, { reset: true }); onSaved(); onClose(); } catch (e) { setErr((e as Error).message); setBusy(false); } };
  return (
    <div className="editor">
      <label>Title<textarea rows={2} value={title} onChange={(e) => setTitle(e.target.value)} maxLength={300} autoFocus /></label>
      <label>{isWaiting ? "Chase on" : "Due date"}
        <span className="date-row">
          <input type="date" value={due} onChange={(e) => setDue(e.target.value)} />
          {canClear && due && <button type="button" className="btn-ghost" onClick={() => setDue("")}>No date</button>}
        </span>
      </label>
      {it.edited && (
        <div className="edited-note">
          Edited here. {it.edited.title_changed && <>Suivi's title: “{it.edited.title}”. </>}
          {it.edited.due_changed && <>Suivi's date: {it.edited.due ? dayShort(it.edited.due) : "none"}. </>}
          <button type="button" className="link-quiet" onClick={reset} disabled={busy}>Reset to the original</button>
        </div>
      )}
      {err && <div className="edit-err">{err}</div>}
      <div className="editor-actions">
        <button type="button" className="btn-small" onClick={save} disabled={busy || !title.trim()}>Save</button>
        <button type="button" className="btn-ghost" onClick={onClose}>Cancel</button>
      </div>
    </div>
  );
}

function Row({ it, today, onToggle, fresh, doneRow, onEdited, onRemind }: { it: Item; today: string; onToggle: (it: Item) => void; fresh: boolean; doneRow?: boolean; onEdited?: () => void; onRemind?: (it: Item) => void }) {
  const over = it.days_overdue > 0 && !it.done;
  const [editing, setEditing] = useState(false);
  const [notesOpen, setNotesOpen] = useState(false);
  const { shown, show, hide } = useReveal(it);
  const [editItemCopy, setEditItemCopy] = useState<Item>(it);
  const startEdit = async () => {
    if (it.masked) { const r = await show(); setEditItemCopy({ ...it, title: r.title }); } else setEditItemCopy(it);
    setEditing(true);
  };
  return (
    <div className={`card ${it.done ? "is-done" : over ? "is-over" : ""} ${fresh ? "glow" : ""}`}>
      <button type="button" className={`chk ${it.done ? "on" : ""}`} onClick={() => onToggle(it)}
        aria-label={(it.done ? "Mark not done: " : "Mark done: ") + it.title}>
        {it.done && <svg className="popin" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M5 12.5l4.5 4.5L19 7.5" /></svg>}
      </button>
      <div className="card-main">
        {editing && onEdited ? <Editor it={editItemCopy} onClose={() => { setEditing(false); hide(); }} onSaved={onEdited} /> : (
          <>
            {it.masked && !shown
              ? <button type="button" className="masked-title" onClick={show} title="Click to show the details">🔒 {it.title} <span>show details</span></button>
              : <div className={`card-title ${it.done ? "struck" : ""}`}>
                  {shown ? shown.title : it.title}
                  {shown && <button type="button" className="link-quiet inline" onClick={hide}>hide</button>}
                </div>}
            <div className="card-meta">
              <span className={`chip chip-${it.weight}`}>{it.weight === "waiting" ? "waiting on" : it.weight}</span>
              {it.person && <span className="meta-small">{it.person}</span>}
              {(shown?.code ?? it.code) && <span className="mono meta-small">{shown?.code ?? it.code}</span>}
              {shown?.person && <span className="meta-small">{shown.person}</span>}
              {it.personal && <span className="chip chip-personal">personal</span>}
              {it.edited && <span className="chip chip-edited" title="You changed this here. Open the editor to see the original.">edited</span>}
              {it.from_note && <span className="chip chip-edited" title="Created from a follow-up note">from a note</span>}
              {doneRow && it.done_at
                ? <span className="due">done {doneTime(it.done_at)}</span>
                : <span className={`due ${over ? "due-over" : ""}`}>{dueLabel(it.due, it.days_overdue, today)}</span>}
            </div>
            {notesOpen && onEdited && <NotesBox parent={{ type: it.type, id: it.id }} onChanged={onEdited} />}
          </>
        )}
      </div>
      {!doneRow && !it.done && onEdited && !editing && (
        <button type="button" className={`note-btn ${it.note_count ? "has" : ""}`} onClick={() => setNotesOpen((o) => !o)} aria-expanded={notesOpen} aria-label={`Notes (${it.note_count})`} title="Notes and follow-ups">📝{it.note_count > 0 && <sup>{it.note_count}</sup>}</button>
      )}
      {!doneRow && !it.done && it.type === "waiting_on" && !it.masked && onRemind && !editing && (
        <button type="button" className="remind-btn" onClick={() => onRemind(it)} title="Draft a reminder to this person">Remind</button>
      )}
      {!doneRow && !it.done && onEdited && !editing && (
        <button type="button" className="edit-btn" onClick={startEdit} aria-label={`Edit: ${it.title}`} title="Edit title or date">✎</button>
      )}
    </div>
  );
}

export default function TodayTab() {
  const [data, setData] = useState<Today | null>(null);
  const [error, setError] = useState(false);
  const [panel, setPanel] = useState<Panel>(null);
  const [celebrate, setCelebrate] = useState(false);
  const [last, setLast] = useState<string | null>(null);
  const [settling, setSettling] = useState<Record<string, boolean>>({});
  const audit = useAuditStatus();
  const timer = useRef<number>();

  const load = useCallback(() => getToday().then((d) => { setData(d); setError(false); }).catch(() => setError(true)), []);
  useEffect(() => { load(); const t = setInterval(load, 60_000); return () => clearInterval(t); }, [load]);

  const toggle = async (it: Item) => {
    const willBeDone = !it.done;
    // Optimistic: update at once so the tick and jet respond instantly, then confirm with the server.
    setData((d) => d && {
      ...d, done_this_week: d.done_this_week + (willBeDone ? 1 : -1),
      today_items: d.today_items.map((x) => (x.key === it.key ? { ...x, done: willBeDone } : x)),
      upcoming_items: d.upcoming_items.map((x) => (x.key === it.key ? { ...x, done: willBeDone } : x)),
    });
    if (willBeDone) {
      // Keep the row in place for a moment so the tick is seen, then it moves to "Done today".
      setSettling((m) => ({ ...m, [it.key]: true }));
      window.setTimeout(() => setSettling((m) => { const { [it.key]: _, ...rest } = m; return rest; }), 1400);
      setCelebrate(true); setLast(it.key);
      window.clearTimeout(timer.current);
      timer.current = window.setTimeout(() => setCelebrate(false), 1300);
    }
    try { await setDone(it, willBeDone); } finally { load(); }
  };
  const tickDeadline = (id: number) => toggle({ key: `deadline:${id}`, type: "deadline", id, done: false } as Item);

  if (error && !data) return <main className="page"><p className="muted">The harness back end isn't reachable. Is it running (make up)?</p></main>;
  if (!data) return <main className="page"><p className="muted">Loading…</p></main>;

  const inOpenList = (i: Item) => !i.done || settling[i.key];
  const openItems = data.today_items.filter(inOpenList);
  const doneToday = data.today_items.filter((i) => i.done && !settling[i.key]).sort((a, b) => (b.done_at ?? "").localeCompare(a.done_at ?? ""));
  const open = data.today_items.filter((i) => !i.done).length;
  return (
    <>
      <Lake data={data} doneCount={data.done_this_week} celebrate={celebrate}
        onOpenDone={() => setPanel({ kind: "done" })} onOpenDeadline={(id) => setPanel({ kind: "deadline", id })} />
      <main className="page grid">
        <section className="panel">
          <div className="panel-head"><h2 className="serif">Today &amp; overdue</h2><span className="muted">{open} open</span></div>
          <div className="sub">What you owe and what is owed to you. Tick it and the jet rises.</div>
          <QuickNote placeholder="A note about today, or a follow-up you want to remember…" onAdded={load} onOpenLog={() => setPanel({ kind: "notes" })} />

          {data.events_today.length > 0 && (
            <div className="events">
              <div className="kicker">ON YOUR CALENDAR TODAY</div>
              {data.events_today.map((e) => (
                <div key={e.id} className="event"><span className="mono">{e.all_day ? "all day" : timeOf(e.start)}</span><span>{e.title}</span></div>
              ))}
            </div>
          )}

          {openItems.length === 0 && <div className="empty">{doneToday.length ? "All done for today. Well done." : "Nothing due today and nothing overdue."}</div>}
          {openItems.map((it) => <Row key={it.key} it={it} today={data.today} onToggle={toggle} fresh={celebrate && last === it.key} onEdited={load} onRemind={(i) => setPanel({ kind: "reminder", id: i.id })} />)}

          {doneToday.length > 0 && (
            <details className="done-today">
              <summary>Done today ({doneToday.length})</summary>
              {doneToday.map((it) => <Row key={it.key} it={it} today={data.today} onToggle={toggle} fresh={false} doneRow />)}
            </details>
          )}
          <button type="button" className="link-quiet" onClick={() => setPanel({ kind: "done" })}>See everything you have done, with dates →</button>

          {data.later_items.length > 0 && (
            <details className="done-today">
              <summary>Later ({data.later_items.length})</summary>
              {data.later_items.map((it) => <Row key={it.key} it={it} today={data.today} onToggle={toggle} fresh={false} onEdited={load} />)}
            </details>
          )}

          {(data.upcoming_items.length > 0 || data.undated_tasks > 0) && (
            <div className="coming">
              <div className="kicker">COMING UP · NEXT 7 DAYS</div>
              {data.upcoming_items.map((it) => <Row key={it.key} it={it} today={data.today} onToggle={toggle} fresh={false} onEdited={load} />)}
              {data.undated_tasks > 0 && <div className="muted small">{data.undated_tasks} more task{data.undated_tasks === 1 ? "" : "s"} without a date.</div>}
            </div>
          )}
        </section>

        <section className="panel">
          <div className="panel-head"><h2 className="serif">Emails needing you</h2></div>
          <QuickNote placeholder="A note about your emails, or a follow-up…" onAdded={load} onOpenLog={() => setPanel({ kind: "notes" })} />
          <EmailList full={false} onChanged={load} />
        </section>

        <aside className="widgets" aria-label="Widgets">
          <button type="button" className="tile tile-live" onClick={() => setPanel({ kind: "calendar" })} aria-label="Open the calendar">
            <div className="tile-art cal-art"><span className="cal-art-dow">{dayShort(data.today).split(" ")[0]}</span><span className="serif cal-art-day">{Number(data.today.slice(8, 10))}</span></div>
            <div className="tile-text">
              <span className="tile-title">Calendar</span>
              <span className="serif tile-head">{data.events_today.length === 0 ? "Nothing today" : `${data.events_today.length} today`}</span>
              <span className="tile-sub">{data.next_event ? `Next: ${dayShort(data.next_event.start)} · ${timeOf(data.next_event.start)} · ${data.next_event.title}` : "No upcoming events"}</span>
              <span className="soon">Day · Week · Month →</span>
            </div>
          </button>
          <AuditTile st={audit.st} onOpen={() => setPanel({ kind: "audit" })} />
          {WIDGETS.map((w) => (
            <div key={w.title} className="tile">
              <div className="tile-art" />
              <div className="tile-text"><span className="tile-title">{w.title}</span>
                <span className="serif tile-head">—</span><span className="tile-sub">{w.sub}</span>
                <span className="soon">Coming in {w.phase}</span></div>
            </div>
          ))}
          <button type="button" className="gallery" disabled>Choose widgets · coming later</button>
        </aside>
      </main>

      <section className="chatbar" aria-label="Harness chat">
        <input type="text" disabled placeholder="Chat, capture and dictation come in Phase 5." />
        <button type="button" disabled>Send</button>
      </section>

      <Drawer panel={panel} today={data.today} onClose={() => setPanel(null)} onTickDeadline={tickDeadline} onChanged={() => { load(); audit.reload(); }} />
    </>
  );
}
