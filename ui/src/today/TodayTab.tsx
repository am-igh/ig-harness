import { useCallback, useEffect, useRef, useState } from "react";
import { type Item, type Today, getToday, setDone } from "../api";
import { dueLabel, timeOf } from "../format";
import Drawer, { type Panel } from "./Drawer";
import Lake from "./Lake";

const WIDGETS = [
  { title: "Audit readiness", sub: "Every payment has its document", phase: "Phase 4" },
  { title: "Hours this week", sub: "Friday pass fills the gaps", phase: "Phase 4" },
  { title: "Budget burn", sub: "Highest open mandate", phase: "Phase 4" },
  { title: "Scan inbox", sub: "Filed automatically", phase: "Phase 4" },
];

function Row({ it, today, onToggle, fresh }: { it: Item; today: string; onToggle: (it: Item) => void; fresh: boolean }) {
  const over = it.days_overdue > 0 && !it.done;
  return (
    <div className={`card ${it.done ? "is-done" : over ? "is-over" : ""} ${fresh ? "glow" : ""}`}>
      <button type="button" className={`chk ${it.done ? "on" : ""}`} onClick={() => onToggle(it)}
        aria-label={(it.done ? "Mark not done: " : "Mark done: ") + it.title}>
        {it.done && <svg className="popin" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M5 12.5l4.5 4.5L19 7.5" /></svg>}
      </button>
      <div className="card-main">
        <div className={`card-title ${it.done ? "struck" : ""}`}>{it.title}</div>
        <div className="card-meta">
          <span className={`chip chip-${it.weight}`}>{it.weight === "waiting" ? "waiting on" : it.weight}</span>
          {it.person && <span className="meta-small">{it.person}</span>}
          {it.code && <span className="mono meta-small">{it.code}</span>}
          {it.personal && <span className="chip chip-personal">personal</span>}
          <span className={`due ${over ? "due-over" : ""}`}>{dueLabel(it.due, it.days_overdue, today)}</span>
        </div>
      </div>
    </div>
  );
}

export default function TodayTab() {
  const [data, setData] = useState<Today | null>(null);
  const [error, setError] = useState(false);
  const [panel, setPanel] = useState<Panel>(null);
  const [celebrate, setCelebrate] = useState(false);
  const [last, setLast] = useState<string | null>(null);
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
      setCelebrate(true); setLast(it.key);
      window.clearTimeout(timer.current);
      timer.current = window.setTimeout(() => setCelebrate(false), 1300);
    }
    try { await setDone(it, willBeDone); } finally { load(); }
  };
  const tickDeadline = (id: number) => toggle({ key: `deadline:${id}`, type: "deadline", id, done: false } as Item);

  if (error && !data) return <main className="page"><p className="muted">The harness back end isn't reachable. Is it running (make up)?</p></main>;
  if (!data) return <main className="page"><p className="muted">Loading…</p></main>;

  const open = data.today_items.filter((i) => !i.done).length;
  return (
    <>
      <Lake data={data} doneCount={data.done_this_week} celebrate={celebrate}
        onOpenDone={() => setPanel({ kind: "done" })} onOpenDeadline={(id) => setPanel({ kind: "deadline", id })} />
      <main className="page grid">
        <section className="panel">
          <div className="panel-head"><h2 className="serif">Today &amp; overdue</h2><span className="muted">{open} open</span></div>
          <div className="sub">What you owe and what is owed to you. Tick it and the jet rises.</div>

          {data.events_today.length > 0 && (
            <div className="events">
              <div className="kicker">ON YOUR CALENDAR TODAY</div>
              {data.events_today.map((e) => (
                <div key={e.id} className="event"><span className="mono">{e.all_day ? "all day" : timeOf(e.start)}</span><span>{e.title}</span></div>
              ))}
            </div>
          )}

          {data.today_items.length === 0 && <div className="empty">Nothing due today and nothing overdue.</div>}
          {data.today_items.map((it) => <Row key={it.key} it={it} today={data.today} onToggle={toggle} fresh={celebrate && last === it.key} />)}

          {(data.upcoming_items.length > 0 || data.undated_tasks > 0) && (
            <div className="coming">
              <div className="kicker">COMING UP · NEXT 7 DAYS</div>
              {data.upcoming_items.map((it) => <Row key={it.key} it={it} today={data.today} onToggle={toggle} fresh={false} />)}
              {data.undated_tasks > 0 && <div className="muted small">{data.undated_tasks} more task{data.undated_tasks === 1 ? "" : "s"} without a date.</div>}
            </div>
          )}
        </section>

        <section className="panel">
          <div className="panel-head"><h2 className="serif">Emails needing you</h2></div>
          <div className="placeholder"><b>Coming in Phase 2</b><span>Gmail triage (read-only) will list the emails that need a reply here. In Phase 3 the harness will draft replies. It never sends.</span></div>
        </section>

        <aside className="widgets" aria-label="Widgets">
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

      <Drawer panel={panel} today={data.today} onClose={() => setPanel(null)} onTickDeadline={tickDeadline} />
    </>
  );
}
