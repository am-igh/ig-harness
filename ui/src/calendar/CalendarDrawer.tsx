import { useEffect, useMemo, useRef, useState } from "react";
import { type CalEventFull, type CalItem, type CalRange, getCalendar } from "../api";
import { Shell } from "../today/Drawer";
import { type View, addDays, dayName, dayOfMonth, daysCovered, genevaParts, hhmm, layoutColumns, monthGrid, monthName, rangeFor, segmentFor, shift, startOfWeek, title, weekday } from "./layout";

const PX_PER_HOUR = 48;
const MAX_CHIPS = 3;
const KEY = "ig-calendar-view";

type Layers = { deadlines: boolean; tasks: boolean };
type Picked = { kind: "event"; e: CalEventFull } | { kind: "item"; i: CalItem } | null;

function timeLabel(e: CalEventFull): string {
  if (e.all_day) return "all day";
  const s = genevaParts(e.start), en = e.end ? genevaParts(e.end) : null;
  return en ? `${hhmm(s.minutes)}–${hhmm(en.minutes)}` : hhmm(s.minutes);
}

/** Everything that happens on one day, in one place: used by the month cells, the week and day headers and the details list. */
function dayContent(data: CalRange | null, day: string, layers: Layers) {
  const events = (data?.events ?? []).filter((e) => daysCovered(e).includes(day));
  const items: CalItem[] = [
    ...(layers.deadlines ? data?.deadlines.filter((d) => d.due === day) ?? [] : []),
    ...(layers.tasks ? [...(data?.tasks.filter((t) => t.due === day) ?? []), ...(data?.waiting.filter((w) => w.due === day) ?? [])] : []),
  ];
  const allDay = events.filter((e) => e.all_day);
  const timed = events.filter((e) => !e.all_day).sort((a, b) => genevaParts(a.start).minutes - genevaParts(b.start).minutes);
  return { allDay, timed, items };
}

function ItemChip({ i, onPick }: { i: CalItem; onPick: (p: Picked) => void }) {
  const cls = i.type === "deadline" ? (i.importance === "major" ? "cal-dl major" : "cal-dl") : i.type === "waiting_on" ? "cal-wt" : "cal-tk";
  const glyph = i.type === "deadline" ? "◆" : i.type === "waiting_on" ? "↺" : "○";
  return <button type="button" className={`cal-chip ${cls}`} onClick={(e) => { e.stopPropagation(); onPick({ kind: "item", i }); }} title={i.title}>{glyph} {i.masked ? "🔒 " : ""}{i.title}</button>;
}

function EventChip({ e, onPick }: { e: CalEventFull; onPick: (p: Picked) => void }) {
  return (
    <button type="button" className={`cal-chip cal-ev ${e.all_day ? "allday" : ""} ${e.tentative ? "tent" : ""}`} onClick={(x) => { x.stopPropagation(); onPick({ kind: "event", e }); }} title={`${timeLabel(e)} ${e.title}`}>
      {!e.all_day && <b>{hhmm(genevaParts(e.start).minutes)}</b>} {e.title}
    </button>
  );
}

function MonthView({ anchor, today, data, layers, onDay, onPick }: { anchor: string; today: string; data: CalRange | null; layers: Layers; onDay: (d: string) => void; onPick: (p: Picked) => void }) {
  const grid = monthGrid(anchor);
  return (
    <div className="cal-month">
      {["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"].map((d) => <div key={d} className="cal-dow">{d}</div>)}
      {grid.map((day) => {
        const c = dayContent(data, day, layers);
        const all = [...c.allDay.map((e) => ({ k: "e" + e.id, node: <EventChip e={e} onPick={onPick} /> })), ...c.timed.map((e) => ({ k: "e" + e.id, node: <EventChip e={e} onPick={onPick} /> })),
          ...c.items.map((i) => ({ k: i.type + i.id, node: <ItemChip i={i} onPick={onPick} /> }))];
        const out = day.slice(0, 7) !== anchor.slice(0, 7);
        return (
          <div key={day} className={`cal-cell ${out ? "out" : ""} ${day === today ? "today" : ""} ${weekday(day) >= 5 ? "weekend" : ""}`} onClick={() => onDay(day)} role="button" tabIndex={0}
            onKeyDown={(e) => e.key === "Enter" && onDay(day)} aria-label={`${dayName(day)} ${dayOfMonth(day)} ${monthName(day)}: ${all.length} item${all.length === 1 ? "" : "s"}`}>
            <span className="cal-num">{dayOfMonth(day)}</span>
            {all.slice(0, MAX_CHIPS).map((x) => <span key={x.k}>{x.node}</span>)}
            {all.length > MAX_CHIPS && <span className="cal-more">+{all.length - MAX_CHIPS} more</span>}
          </div>
        );
      })}
    </div>
  );
}

function TimeGrid({ days, today, data, layers, onDay, onPick }: { days: string[]; today: string; data: CalRange | null; layers: Layers; onDay: (d: string) => void; onPick: (p: Picked) => void }) {
  const scroller = useRef<HTMLDivElement>(null);
  const contents = days.map((d) => dayContent(data, d, layers));
  // Show 07:00–21:00 at least, wider if something happens earlier or later.
  const segs = days.flatMap((d, k) => contents[k].timed.map((e) => segmentFor(e, d)).filter(Boolean) as { startMin: number; endMin: number }[]);
  const startH = Math.min(7, ...segs.map((s) => Math.floor(s.startMin / 60)));
  const endH = Math.max(21, ...segs.map((s) => Math.ceil(s.endMin / 60)));
  const hours = Array.from({ length: endH - startH }, (_, i) => startH + i);
  const [nowMin, setNowMin] = useState(() => { const p = genevaParts(new Date().toISOString()); return p.date === today ? p.minutes : -1; });
  useEffect(() => { const t = setInterval(() => { const p = genevaParts(new Date().toISOString()); setNowMin(p.date === today ? p.minutes : -1); }, 60_000); return () => clearInterval(t); }, [today]);
  useEffect(() => {          // open scrolled to the first event of the period (or 07:30)
    const first = segs.length ? Math.min(...segs.map((s) => s.startMin)) : 7.5 * 60;
    if (scroller.current) scroller.current.scrollTop = Math.max(0, ((first - startH * 60) / 60) * PX_PER_HOUR - 24);
  }, [days.join(","), data]);       // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="cal-grid-wrap">
      <div className="cal-gh" style={{ gridTemplateColumns: `52px repeat(${days.length}, 1fr)` }}>
        <div />
        {days.map((d, k) => (
          <div key={d} className={`cal-dayhead ${d === today ? "today" : ""}`}>
            <button type="button" onClick={() => onDay(d)} title="Open this day">{dayName(d).slice(0, 3)} <b>{dayOfMonth(d)}</b></button>
            <div className="cal-allday">
              {contents[k].allDay.map((e) => <EventChip key={"e" + e.id} e={e} onPick={onPick} />)}
              {contents[k].items.map((i) => <ItemChip key={i.type + i.id} i={i} onPick={onPick} />)}
            </div>
          </div>
        ))}
      </div>
      <div className="cal-scroll" ref={scroller}>
        <div className="cal-body" style={{ gridTemplateColumns: `52px repeat(${days.length}, 1fr)`, height: hours.length * PX_PER_HOUR }}>
          <div className="cal-hours">{hours.map((h) => <div key={h} style={{ height: PX_PER_HOUR }}><span>{String(h).padStart(2, "0")}:00</span></div>)}</div>
          {days.map((d, k) => {
            const items = contents[k].timed.map((e) => ({ e, seg: segmentFor(e, d)! })).filter((x) => x.seg);
            const lay = layoutColumns(items.map((x) => ({ id: x.e.id, startMin: x.seg.startMin, endMin: x.seg.endMin })));
            return (
              <div key={d} className={`cal-col ${d === today ? "today" : ""}`} style={{ backgroundSize: `100% ${PX_PER_HOUR}px` }}>
                {items.map(({ e, seg }) => {
                  const l = lay.get(e.id)!;
                  return (
                    <button type="button" key={e.id} className={`cal-block ${e.tentative ? "tent" : ""}`} onClick={() => onPick({ kind: "event", e })}
                      style={{ top: ((seg.startMin - startH * 60) / 60) * PX_PER_HOUR, height: ((seg.endMin - seg.startMin) / 60) * PX_PER_HOUR - 2, left: `${(l.col / l.cols) * 100}%`, width: `calc(${100 / l.cols}% - 3px)` }}
                      title={`${timeLabel(e)} ${e.title}`}>
                      <b>{hhmm(seg.startMin)}</b> {e.title}
                    </button>
                  );
                })}
                {d === today && nowMin >= startH * 60 && nowMin <= endH * 60 && <div className="cal-now" style={{ top: ((nowMin - startH * 60) / 60) * PX_PER_HOUR }} />}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

export default function CalendarDrawer({ today, onClose }: { today: string; onClose: () => void }) {
  const saved = (() => { try { return localStorage.getItem(KEY) as View | null; } catch { return null; } })();
  const [view, setView] = useState<View>(saved === "day" || saved === "week" || saved === "month" ? saved : "week");
  const [anchor, setAnchor] = useState(today);
  const [layers, setLayers] = useState<Layers>({ deadlines: true, tasks: true });
  const [data, setData] = useState<CalRange | null>(null);
  const [err, setErr] = useState("");
  const [picked, setPicked] = useState<Picked>(null);
  const range = useMemo(() => rangeFor(view, anchor), [view, anchor]);

  useEffect(() => { try { localStorage.setItem(KEY, view); } catch { /* remembered view is a convenience only */ } }, [view]);
  useEffect(() => { let live = true; getCalendar(range.start, range.end).then((d) => { if (live) { setData(d); setErr(""); } }).catch((e) => live && setErr(e.message)); return () => { live = false; }; }, [range.start, range.end]);
  useEffect(() => {
    const h = (e: KeyboardEvent) => {
      if ((e.target as HTMLElement)?.tagName === "INPUT") return;
      if (e.key === "ArrowLeft") setAnchor((a) => shift(view, a, -1));
      if (e.key === "ArrowRight") setAnchor((a) => shift(view, a, 1));
    };
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [view]);

  const days = view === "day" ? [anchor] : Array.from({ length: 7 }, (_, i) => addDays(startOfWeek(anchor), i));
  const outside = data?.coverage.from && (range.end < data.coverage.from || (data.coverage.to && range.start > data.coverage.to));
  const open = (d: string) => { setAnchor(d); setView("day"); setPicked(null); };
  const go = (dir: 1 | -1) => { setAnchor((a) => shift(view, a, dir)); setPicked(null); };

  return (
    <Shell kicker="CALENDAR" title={title(view, anchor)} meta="Your Google Calendar, with deadlines and tasks. Times are Geneva time." onClose={onClose} wide>
      <div className="cal-bar">
        <div className="cal-nav">
          <button type="button" className="btn-ghost" onClick={() => go(-1)} aria-label="Previous">‹</button>
          <button type="button" className="btn-ghost" onClick={() => { setAnchor(today); setPicked(null); }}>Today</button>
          <button type="button" className="btn-ghost" onClick={() => go(1)} aria-label="Next">›</button>
        </div>
        <div className="range" role="group" aria-label="View">
          {(["day", "week", "month"] as View[]).map((v) => <button key={v} type="button" className={v === view ? "on" : ""} aria-pressed={v === view} onClick={() => { setView(v); setPicked(null); }}>{v[0].toUpperCase() + v.slice(1)}</button>)}
        </div>
        <label className="cal-layer"><input type="checkbox" checked={layers.deadlines} onChange={(e) => setLayers({ ...layers, deadlines: e.target.checked })} /> <span className="cal-dl">◆</span> Deadlines</label>
        <label className="cal-layer"><input type="checkbox" checked={layers.tasks} onChange={(e) => setLayers({ ...layers, tasks: e.target.checked })} /> <span className="cal-tk">○</span> Tasks &amp; chase dates</label>
      </div>
      {err && <div className="edit-err">{err}</div>}
      {outside && <div className="notice">There is no calendar data for this period yet. The harness reads from {data?.coverage.from} to {data?.coverage.to}.</div>}

      {view === "month"
        ? <MonthView anchor={anchor} today={today} data={data} layers={layers} onDay={open} onPick={setPicked} />
        : <TimeGrid days={days} today={today} data={data} layers={layers} onDay={open} onPick={setPicked} />}

      {picked && (
        <div className="cal-detail" role="status">
          {picked.kind === "event" ? (
            <><b>{picked.e.title}</b><span>{timeLabel(picked.e)}{picked.e.all_day && picked.e.end ? ` · ${picked.e.start.slice(0, 10)} to ${addDays(picked.e.end.slice(0, 10), -1)}` : ""}{picked.e.tentative ? " · tentative" : ""}</span></>
          ) : (
            <><b>{picked.i.masked ? "🔒 " : ""}{picked.i.title}</b><span>{picked.i.type === "deadline" ? "Deadline" : picked.i.type === "waiting_on" ? "Chase date" : "Task due"} · {picked.i.due}{picked.i.masked ? " · details are hidden; open it on the Today board" : ""}</span></>
          )}
          <button type="button" className="link-quiet" onClick={() => setPicked(null)}>close</button>
        </div>
      )}
      <div className="note">Click a day to open it. Arrow keys move between periods. Calendar events are read-only here: the harness never changes your calendar.</div>
    </Shell>
  );
}
