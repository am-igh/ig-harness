import { useEffect, useRef, useState } from "react";
import { dayMonth, daysBetween } from "../format";
import { jetPaths } from "../today/Lake";

/** The shared "band" that echoes the Jet d'eau lake on Today: a deep navy landscape with a time axis and clickable marks.
 *  Three landscapes: "horizon" (Geneva and beyond: the lake, the Alps and the world beyond), "rhone" (Projects & finance: the river that leaves the lake, one stream per project),
 *  "harbor" (Inbox: the Jet d'eau and the boats at anchor). */
export type Tone = "confirmed" | "maybe" | "invited" | "info" | "major" | "normal" | "done";
export type SceneMark = { id: string; label: string; date: string; tone: Tone; ring?: boolean; onClick?: () => void; title?: string };
export type SceneLane = { code: string; name: string; marks: SceneMark[] };
type Legend = { color: string; label: string; ring?: boolean };
type Props = {
  variant: "horizon" | "rhone" | "harbor"; today: string; kicker: string; headline: string; sub?: string; stat?: { value: string | number; label: string; hint?: string };
  marks?: SceneMark[]; lanes?: SceneLane[]; legend: Legend[]; minSpan?: number; maxSpan?: number; empty?: string; note?: string;
};

const TODAY_X = 300;
const LANES = [50, 72, 94, 116, 138];
const LABEL_GAP = 170;
export const TONE: Record<Tone, string> = { confirmed: "#B845B8", maybe: "#D9A6D9", invited: "#AEB9E8", info: "#8F9DD6", major: "#E8A300", normal: "#AEB9E8", done: "#BAD403" };

function Stars() {
  const pts = [[60, 20], [140, 44], [220, 16], [420, 28], [510, 52], [610, 18], [700, 40], [820, 24], [930, 46], [1010, 14], [1120, 30], [1230, 18], [1320, 42], [1400, 22], [360, 60], [880, 62]];
  return <g fill="#fff" fillOpacity=".38">{pts.map(([x, y], i) => <circle key={i} cx={x} cy={y} r={i % 3 === 0 ? 1.3 : 0.9} />)}</g>;
}

function Water() {
  return (
    <>
      <rect x="0" y="160" width="1440" height="60" fill="#12234A" />
      <g className="sc-waves">
        <path d="M0 178 C 60 174, 120 182, 180 178 S 300 174, 360 178 S 480 182, 540 178 S 660 174, 720 178 S 840 182, 900 178 S 1020 174, 1080 178 S 1200 182, 1260 178 S 1380 174, 1440 178" fill="none" stroke="#6A7BC1" strokeOpacity=".28" strokeWidth="1.5" />
        <path d="M0 196 C 80 192, 160 200, 240 196 S 400 192, 480 196 S 640 200, 720 196 S 880 192, 960 196 S 1120 200, 1200 196 S 1360 192, 1440 196" fill="none" stroke="#6A7BC1" strokeOpacity=".18" strokeWidth="1.5" />
      </g>
      <line x1="0" y1="160" x2="1440" y2="160" stroke="#8F9DD6" strokeOpacity=".75" strokeWidth="2" />
    </>
  );
}

function HorizonArt() {
  return (
    <svg width="100%" height="220" viewBox="0 0 1440 220" preserveAspectRatio="none" className="lake-bg" aria-hidden="true">
      <Stars />
      <path d="M0 220 C 400 70, 900 24, 1440 76" fill="none" stroke="#6A7BC1" strokeOpacity=".16" strokeWidth="1.2" strokeDasharray="3 7" />
      <path d="M0 200 C 450 46, 1000 0, 1440 44" fill="none" stroke="#6A7BC1" strokeOpacity=".12" strokeWidth="1.2" strokeDasharray="3 7" />
      <path className="sc-contrail" d="M720 124 C 900 96, 1120 60, 1330 24" fill="none" stroke="#AEB9E8" strokeOpacity=".4" strokeWidth="1.4" strokeDasharray="2 7" />
      <path d="M1327 20 L1343 22 L1332 28 Z" fill="#DDE3F6" fillOpacity=".8" />
      <path d="M300 160 L350 134 L392 144 L462 108 L510 128 L572 98 L640 130 L712 110 L790 140 L870 94 L930 122 L1010 72 L1050 98 L1105 42 L1145 84 L1205 66 L1255 112 L1325 92 L1440 126 L1440 160 Z" fill="#1B3057" />
      <path d="M0 152 C 90 124, 190 130, 300 152 L300 160 L0 160 Z" fill="#1E3660" />
      <path d="M1105 42 L1092 64 L1104 58 L1112 66 L1118 58 L1128 66 L1117 52 Z" fill="#DDE3F6" fillOpacity=".42" />
      <path d="M1010 72 L1000 88 L1010 83 L1018 90 L1024 82 Z" fill="#DDE3F6" fillOpacity=".3" />
      <path d="M570 98 L562 112 L571 107 L578 113 Z" fill="#DDE3F6" fillOpacity=".25" />
      <path d="M0 138 C 150 112, 300 126, 460 120 S 780 112, 980 126 S 1260 118, 1440 130 L1440 160 L0 160 Z" fill="#1E3660" fillOpacity=".55" />
      <Water />
    </svg>
  );
}

function HarborArt() {
  const boat = (x: number, s: number, delay: number) => (
    <g key={x} className="sc-boat" style={{ animationDelay: `${delay}s` }} transform={`translate(${x} 152) scale(${s})`}>
      <path d="M0 0 L46 0 L40 8 L8 8 Z" fill="#DDE3F6" fillOpacity=".85" />
      <line x1="22" y1="0" x2="22" y2="-50" stroke="#DDE3F6" strokeOpacity=".7" strokeWidth="1.4" />
      <path d="M21 -48 L21 -4 L-4 -6 Z" fill="#fff" fillOpacity=".88" />
      <path d="M23 -40 L23 -4 L48 -5 Z" fill="#AEB9E8" fillOpacity=".8" />
    </g>
  );
  const gull = (x: number, y: number, s = 1) => <path key={`${x}${y}`} className="sc-gull" d={`M${x} ${y} q ${6 * s} ${-7 * s} ${12 * s} 0 q ${6 * s} ${-7 * s} ${12 * s} 0`} fill="none" stroke="#fff" strokeOpacity=".55" strokeWidth="1.5" strokeLinecap="round" />;
  return (
    <svg width="100%" height="220" viewBox="0 0 1440 220" preserveAspectRatio="none" className="lake-bg" aria-hidden="true">
      <Stars />
      <path d="M0 152 C 80 140, 160 146, 260 150 L260 160 L0 160 Z" fill="#1E3660" />
      <path d="M340 160 C 420 146, 560 150, 700 148 S 1000 140, 1180 148 S 1360 144, 1440 148 L1440 160 Z" fill="#1E3660" />
      <g fill="#E8A300" fillOpacity=".6">{[380, 420, 470, 530, 590, 650, 760, 840, 905, 980, 1060, 1140, 1230, 1310].map((x, i) => <circle key={x} cx={x} cy={150 + (i % 3)} r="1.2" />)}</g>
      {gull(520, 52)}{gull(560, 38, 0.8)}{gull(790, 30, 1.1)}{gull(1030, 60)}{gull(1180, 42, 0.9)}
      {boat(470, 0.9, 0)}{boat(720, 1.1, 1.2)}{boat(1010, 0.8, 2.4)}{boat(1230, 1, 0.6)}
      <Water />
    </svg>
  );
}

function RhoneArt({ ys }: { ys: number[] }) {
  return (
    <svg width="100%" height="220" viewBox="0 0 1440 220" preserveAspectRatio="none" className="lake-bg" aria-hidden="true">
      <Stars />
      <path d="M700 160 C 860 92, 1130 52, 1440 66 L1440 160 Z" fill="#22407A" />
      {[0, 1, 2, 3, 4, 5].map((i) => <path key={i} d={`M${740 + i * 16} ${152 - i * 4} C 940 ${98 + i * 9}, 1160 ${70 + i * 9}, 1440 ${80 + i * 9}`} fill="none" stroke="#4C78C4" strokeOpacity=".85" strokeWidth="1.3" />)}
      <g fill="#DDE3F6" fillOpacity=".55">{[1010, 1060, 1180, 1240, 1330].map((x, i) => <rect key={x} x={x} y={94 + i * 6} width="8" height="5" />)}<rect x="1300" y="84" width="3" height="12" /></g>
      <path d="M0 150 C 90 124, 190 132, 290 150 L290 160 L0 160 Z" fill="#1E3660" />
      <rect x="0" y="160" width="1440" height="60" fill="#12234A" />
      <g fill="none" stroke="#AEB9E8" strokeOpacity=".75" strokeWidth="2.6">
        <path d="M236 160 L236 134 L380 134 L380 160" />
        {[0, 1, 2].map((i) => <path key={i} d={`M${244 + i * 45} 160 A 19 24 0 0 1 ${282 + i * 45} 160`} />)}
      </g>
      {ys.map((y, i) => (
        <g key={i}>
          <path d={`M300 ${y} C 420 ${y - 6}, 520 ${y + 6}, 640 ${y} S 900 ${y - 6}, 1040 ${y} S 1300 ${y + 6}, 1440 ${y}`} fill="none" stroke="#6A7BC1" strokeOpacity=".28" strokeWidth="11" strokeLinecap="round" />
          <path className="sc-flow" d={`M300 ${y} C 420 ${y - 6}, 520 ${y + 6}, 640 ${y} S 900 ${y - 6}, 1040 ${y} S 1300 ${y + 6}, 1440 ${y}`} fill="none" stroke="#DDE3F6" strokeOpacity=".5" strokeWidth="1.6" strokeDasharray="6 16" />
        </g>
      ))}
    </svg>
  );
}

function Jet() {
  const jet = jetPaths(5);
  return (
    <svg width="360" height="220" viewBox="0 0 360 220" className="lake-jet" aria-hidden="true">
      <ellipse cx="300" cy="160" rx="30" ry="6" fill="#fff" fillOpacity=".18" />
      <path d={jet.mist} fill="none" stroke="#fff" strokeOpacity=".22" strokeWidth="12" strokeLinecap="round" />
      <path d={jet.plume2} fill="none" stroke="#fff" strokeOpacity=".38" strokeWidth="8" strokeLinecap="round" />
      <path d={jet.plume1} fill="none" stroke="#fff" strokeOpacity=".6" strokeWidth="5" strokeLinecap="round" />
      <path d={jet.column} fill="#fff" fillOpacity=".93" />
      {jet.drops.map((d, i) => <circle key={i} cx={d.x} cy={d.y} r={d.r} fill="#DDE3F6" fillOpacity=".8" />)}
      <ellipse cx="300" cy="160" rx="16" ry="4" fill="#fff" fillOpacity=".7" />
    </svg>
  );
}

export default function Scene({ variant, today, kicker, headline, sub, stat, marks = [], lanes = [], legend, minSpan = 28, maxSpan = 120, empty, note }: Props) {
  const ref = useRef<HTMLElement>(null);
  const [w, setW] = useState(1440);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const ro = new ResizeObserver(() => setW(Math.max(900, el.clientWidth)));
    ro.observe(el); setW(Math.max(900, el.clientWidth));
    return () => ro.disconnect();
  }, []);
  const all = variant === "rhone" ? lanes.flatMap((l) => l.marks) : marks;
  const last = Math.max(0, ...all.map((m) => daysBetween(today, m.date)));
  const span = Math.min(maxSpan, Math.max(minSpan, last + 4));
  const x0 = variant === "rhone" ? TODAY_X + 95 : TODAY_X + 80;          // the time axis starts a little right of the jet so labels stay clear of the title
  const width = w - x0 - 60;
  // The near term gets more room than the far future (a gentle curve), so a busy fortnight is readable.
  const px = (iso: string) => {
    const d = Math.max(0, daysBetween(today, iso));
    return Math.round(x0 + width * (variant === "rhone" ? Math.min(1, d / span) : Math.min(1, Math.pow(d / span, 0.62))));
  };
  const end = new Date(today + "T12:00:00"); end.setDate(end.getDate() + span);
  const endIso = end.toISOString().slice(0, 10);

  let content: React.ReactNode = null;
  let ys: number[] = [];
  if (variant === "rhone") {
    const n = Math.max(1, lanes.length);
    ys = lanes.map((_, i) => (n === 1 ? 100 : Math.round(48 + (i * 112) / (n - 1))));
    content = lanes.map((lane, li) => {
      let lastLabelX = -1e9;
      return (
        <div key={lane.code}>
          <span className="rv-code" style={{ left: TODAY_X + 8, top: ys[li] - 20 }} title={lane.name}>{lane.code}</span>
          {lane.marks.map((m) => {
            const x = px(m.date);
            const showLabel = x - lastLabelX >= 130;
            if (showLabel) lastLabelX = x;
            return (
              <button key={m.id} type="button" className={`rv-mark tone-${m.tone}`} style={{ left: x - 7, top: ys[li] - 7 }} onClick={m.onClick} title={m.title ?? `${m.label} · ${dayMonth(m.date)}`}
                aria-label={`${lane.code}: ${m.label}, ${dayMonth(m.date)}`}>
                <span className="rv-dot" style={{ background: m.ring ? "transparent" : TONE[m.tone], borderColor: TONE[m.tone] }} />
                {showLabel && <span className="rv-label">{m.label.length > 22 ? m.label.slice(0, 21) + "…" : m.label}</span>}
              </button>
            );
          })}
        </div>
      );
    });
  } else {
    // Labels go to the most important marks first (you're in, then major...), each in a free lane; marks that find no room are shown as dots (hover for the title).
    const PRIORITY: Tone[] = ["confirmed", "major", "maybe", "invited", "info", "normal", "done"];
    const laneOf = new Map<string, number>();
    [...marks].sort((a, b) => PRIORITY.indexOf(a.tone) - PRIORITY.indexOf(b.tone) || a.date.localeCompare(b.date)).forEach((m) => {
      const x = px(m.date);
      // a lane is free only if no label already placed there is within reach on either side
      const ok = LANES.map((_, i) => i).find((i) => marks.every((o) => o === m || laneOf.get(o.id) !== i || Math.abs(px(o.date) - x) >= LABEL_GAP));
      if (ok !== undefined) laneOf.set(m.id, ok);
    });
    let lastDateX = -1e9;
    content = [...marks].sort((a, b) => a.date.localeCompare(b.date)).map((m) => {
      const x = px(m.date);
      const lane = laneOf.get(m.id);
      const showDate = x - lastDateX >= 54;
      if (showDate) lastDateX = x;
      const size = m.tone === "confirmed" ? 16 : 12, top = lane === undefined ? 150 : LANES[lane];
      const dot = <span className={`mk-dot ${m.tone === "confirmed" ? "sc-glow" : ""}`} style={{ width: size, height: size, background: m.ring ? "transparent" : TONE[m.tone], borderColor: m.ring ? TONE[m.tone] : "var(--deep)" }} />;
      return (
        <span key={m.id}>
          <button type="button" className="mark" onClick={m.onClick} title={m.title ?? m.label} aria-label={`${m.label}, ${dayMonth(m.date)}`} style={{ left: x - 70, top, height: 160 - top + size / 2 }}>
            {lane !== undefined && <span className="mk-label">{m.label.length > 24 ? m.label.slice(0, 23) + "…" : m.label}</span>}
            {lane !== undefined && <span className="mk-line" />}
            {lane === undefined && <span style={{ flexGrow: 1 }} />}
            {dot}
          </button>
          {showDate && <div className="mk-date" style={{ left: x - 40 }}>{dayMonth(m.date)}</div>}
        </span>
      );
    });
  }

  return (
    <section ref={ref} className={`lake scene scene-${variant}`} aria-label={headline}>
      {variant === "horizon" && <HorizonArt />}{variant === "harbor" && <HarborArt />}{variant === "rhone" && <RhoneArt ys={ys} />}
      {variant === "harbor" || variant === "horizon" ? <Jet /> : null}
      <div className="lake-greet">
        <div className="kicker-light">{kicker}</div>
        <div className="serif greet sc-headline">{headline}</div>
        {sub && <div className="greet-date">{sub}</div>}
      </div>
      {stat && (
        <div className="done-pill sc-stat">
          <span className="done-count serif">{stat.value}</span>
          <span className="done-text"><b>{stat.label}</b>{stat.hint && <small>{stat.hint}</small>}</span>
        </div>
      )}
      <div className="lake-legend sc-legend">
        <span className="kicker-light">{dayMonth(today).toUpperCase()} → {dayMonth(endIso).toUpperCase()}</span>
        {legend.map((l) => <span key={l.label}><i style={l.ring ? { background: "transparent", border: `2px solid ${l.color}`, width: 9, height: 9 } : { background: l.color }} />{l.label}</span>)}
        {note && <span>· {note}</span>}
      </div>
      {content}
      {all.length === 0 && empty && <div className="sc-empty">{empty}</div>}
      {variant !== "rhone" && <div className="today-label">Today</div>}
    </section>
  );
}
