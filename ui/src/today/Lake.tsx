import { useEffect, useRef, useState } from "react";
import type { Today } from "../api";
import { dayMonth, daysBetween, headerDate, timeOf, dayShort } from "../format";

export const LAKE_DAYS = 47;     // the API looks this far ahead; the lake zooms to fit what it finds
const MIN_SPAN = 21;
const TODAY_X = 300;
const LANES = [50, 70, 90, 110, 130];
const LABEL_GAP = 168;   // min distance between labels sharing a lane

const dotColor = (m: Today["lake"][number]) =>
  m.importance === "major" ? "#E8A300" : m.kind === "fixed" ? "#AEB9E8" : "#AEB9E8";

/** Jet height grows with the number of items done this week (kept from the approved mockup). */
export function jetPaths(n: number) {
  const T = Math.max(14, 160 - (44 + n * 8));
  return {
    column: `M295 160 L298.6 ${T + 6} Q300 ${T} 301.4 ${T + 6} L305 160 Z`,
    plume1: `M300 ${T + 2} C 304 ${T - 10}, 318 ${T - 6}, 324 ${T + 22}`,
    plume2: `M301 ${T + 8} C 308 ${T + 2}, 322 ${T + 12}, 330 ${T + 48}`,
    mist: `M302 ${T + 20} C 312 ${T + 24}, 326 ${T + 46}, 334 ${T + 84}`,
    drops: [[318, 34, 1.6], [326, 58, 1.3], [312, 20, 1.2], [332, 74, 1.1], [339, 96, 1]].map(
      ([x, y, r]) => ({ x, y: Math.min(156, T + y), r })),
  };
}

type Props = {
  data: Today; doneCount: number; celebrate: boolean;
  onOpenDone: () => void; onOpenDeadline: (id: number) => void;
};

export default function Lake({ data, doneCount, celebrate, onOpenDone, onOpenDeadline }: Props) {
  const ref = useRef<HTMLElement>(null);
  const [w, setW] = useState(1440);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const ro = new ResizeObserver(() => setW(Math.max(900, el.clientWidth)));
    ro.observe(el);
    setW(Math.max(900, el.clientWidth));
    return () => ro.disconnect();
  }, []);

  // Zoom the time axis to the deadlines: at least 3 weeks, up to just past the last one.
  const lastDays = Math.max(0, ...data.lake.map((m) => daysBetween(data.today, m.due)));
  const span = Math.min(LAKE_DAYS, Math.max(MIN_SPAN, lastDays + 4));
  const perDay = (w - TODAY_X - 70) / span;
  const px = (iso: string) => Math.round(TODAY_X + daysBetween(data.today, iso) * perDay);
  const jet = jetPaths(doneCount);

  // Spread labels over three lanes so neighbouring deadlines don't collide.
  const lastX = LANES.map(() => -1e9);
  let lastDateX = -1e9;
  const marks = data.lake.map((m) => {
    const x = px(m.due);
    let lane = lastX.findIndex((lx) => x - lx >= LABEL_GAP);
    if (lane < 0) lane = lastX.indexOf(Math.min(...lastX));
    lastX[lane] = x;
    const showDate = x - lastDateX >= 54;
    if (showDate) lastDateX = x;
    return { m, x, lane, showDate };
  });

  const end = new Date(data.today + "T12:00:00");
  end.setDate(end.getDate() + span);

  return (
    <section ref={ref} aria-label="Deadlines ahead" className="lake">
      <svg width="100%" height="220" viewBox="0 0 1440 220" preserveAspectRatio="none" className="lake-bg" aria-hidden="true">
        <path d="M0 138 C 150 112, 300 126, 460 108 S 780 88, 980 112 S 1260 98, 1440 118 L1440 160 L0 160 Z" fill="#1E3660" />
        <path d="M0 150 C 200 136, 420 146, 640 134 S 1060 128, 1440 142 L1440 160 L0 160 Z" fill="#223C69" />
        <rect x="0" y="160" width="1440" height="60" fill="#12234A" />
        <path d="M0 178 C 60 174, 120 182, 180 178 S 300 174, 360 178 S 480 182, 540 178 S 660 174, 720 178 S 840 182, 900 178 S 1020 174, 1080 178 S 1200 182, 1260 178 S 1380 174, 1440 178" fill="none" stroke="#6A7BC1" strokeOpacity=".28" strokeWidth="1.5" />
        <path d="M0 196 C 80 192, 160 200, 240 196 S 400 192, 480 196 S 640 200, 720 196 S 880 192, 960 196 S 1120 200, 1200 196 S 1360 192, 1440 196" fill="none" stroke="#6A7BC1" strokeOpacity=".18" strokeWidth="1.5" />
        <line x1="0" y1="160" x2="1440" y2="160" stroke="#8F9DD6" strokeOpacity=".75" strokeWidth="2" />
      </svg>
      <svg width="360" height="220" viewBox="0 0 360 220" className="lake-jet" aria-hidden="true">
        <g className={celebrate ? "surge" : ""} style={{ transformOrigin: "300px 160px" }}>
          <ellipse cx="300" cy="160" rx="30" ry="6" fill="#fff" fillOpacity=".18" />
          <path className="mist" d={jet.mist} fill="none" stroke="#fff" strokeOpacity=".22" strokeWidth="12" strokeLinecap="round" />
          <path d={jet.plume2} fill="none" stroke="#fff" strokeOpacity=".38" strokeWidth="8" strokeLinecap="round" />
          <path d={jet.plume1} fill="none" stroke="#fff" strokeOpacity=".6" strokeWidth="5" strokeLinecap="round" />
          <path d={jet.column} fill="#fff" fillOpacity=".93" />
          {jet.drops.map((d, i) => <circle key={i} cx={d.x} cy={d.y} r={d.r} fill="#DDE3F6" fillOpacity=".8" />)}
          <ellipse cx="300" cy="160" rx="16" ry="4" fill="#fff" fillOpacity=".7" />
        </g>
        <line x1="288" y1="170" x2="312" y2="170" stroke="#fff" strokeOpacity=".35" strokeWidth="2" strokeLinecap="round" />
        <line x1="284" y1="182" x2="316" y2="182" stroke="#fff" strokeOpacity=".18" strokeWidth="2" strokeLinecap="round" />
      </svg>

      <div className="lake-greet">
        <div className="serif greet">Bonjour, Anne-Marie</div>
        <div className="greet-date">{headerDate(data.now)}</div>
      </div>
      <button type="button" className="done-pill" onClick={onOpenDone}>
        <span className="done-count serif">{doneCount}</span>
        <span className="done-text"><b>done this week</b><small>the jet rises with each one</small></span>
      </button>
      {celebrate && (
        <div className="sparks">
          {["#7D147D", "#E8A300", "#BAD403", "#6A7BC1", "#86858A"].map((c, i) => (
            <span key={i} className="spark" style={{ background: c, animationDelay: `${i * 0.06}s` }} />
          ))}
        </div>
      )}

      <div className="lake-legend">
        <span className="kicker-light">DEADLINES AHEAD · {dayMonth(data.today).toUpperCase()} → {dayMonth(end.toISOString().slice(0, 10)).toUpperCase()}</span>
        <span><i style={{ background: "#E8A300" }} />major</span>
        <span><i style={{ background: "#AEB9E8" }} />fixed date</span>
        <span>· ticks are D-14 / D-3 warnings · click any date</span>
      </div>
      {data.next_event && (
        <div className="next-event">
          <b>Next on your calendar</b>{dayShort(data.next_event.start)} · {timeOf(data.next_event.start)} · {data.next_event.title}
        </div>
      )}

      {data.ticks.filter((t) => daysBetween(data.today, t) <= span).map((t) => (
        <div key={t} className="tick" style={{ left: px(t) }} />
      ))}
      {marks.map(({ m, x, lane, showDate }) => {
        const size = m.importance === "major" ? 16 : 12;
        const top = LANES[lane];
        return (
          <span key={m.id}>
            <button type="button" className="mark" onClick={() => onOpenDeadline(m.id)} title={m.title}
              aria-label={`Open deadline: ${m.title}, ${dayMonth(m.due)}`}
              style={{ left: x - 70, top, height: 160 - top + size / 2 }}>
              <span className="mk-label">{m.title.length > 24 ? m.title.slice(0, 23) + "…" : m.title}</span>
              <span className="mk-line" />
              <span className="mk-dot" style={{ width: size, height: size, background: dotColor(m) }} />
            </button>
            {showDate && <div className="mk-date" style={{ left: x - 40 }}>{dayMonth(m.due)}</div>}
          </span>
        );
      })}
      <div className="today-label">Today</div>
    </section>
  );
}
