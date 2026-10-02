import { useCallback, useEffect, useState } from "react";
import { type EventDetail, type EventItem, type EventsResponse, getEvent, getEvents, hideEvent, setEventStatus } from "../api";
import { dayMonth, dayShort, timeOf } from "../format";
import { Shell } from "../today/Drawer";

const STATUS_LABEL: Record<string, string> = { confirmed: "You're in", tentative: "Maybe", invited: "Invited", interested: "Interested", declined: "Not going", none: "" };
const ROLE_LABEL: Record<string, string> = { moderator: "Moderating", facilitator: "Facilitating", speaker: "Speaking", panelist: "Panelist", judge: "Judging", mentor: "Mentoring" };

function when(e: EventItem): string {
  const d1 = e.start.slice(0, 10);
  const endIso = e.end ? e.end.slice(0, 10) : d1;
  if (e.all_day) {
    const last = new Date(new Date(endIso + "T12:00:00").getTime() - 86400000).toISOString().slice(0, 10);       // Google's all-day end is exclusive
    return last > d1 ? `${dayMonth(d1)} to ${dayMonth(last)}` : dayShort(d1);
  }
  return `${dayShort(d1)} · ${timeOf(e.start)}${e.end ? `–${timeOf(e.end)}` : ""}`;
}

function weekLabel(iso: string): string {
  const d = new Date(iso.slice(0, 10) + "T12:00:00");
  const monday = new Date(d.getTime() - ((d.getDay() + 6) % 7) * 86400000);
  return `Week of ${dayMonth(monday.toISOString().slice(0, 10))}`;
}

function Card({ e, onOpen }: { e: EventItem; onOpen: () => void }) {
  return (
    <button type="button" className={`ev-card ev-${e.status}`} onClick={onOpen} aria-label={`${e.title}, ${STATUS_LABEL[e.status] || "no response"}`}>
      <div className="ev-when">{when(e)}</div>
      <div className="ev-main">
        <div className="ev-title serif">{e.title}</div>
        <div className="ev-sub">{[e.venue, e.online && !e.venue ? "Online" : null].filter(Boolean).join(" · ") || (e.online ? "Online" : "")}</div>
        <div className="ev-chips">
          {e.status === "confirmed" && <span className="ev-badge">✓ You're in</span>}
          {e.status !== "confirmed" && STATUS_LABEL[e.status] && <span className={`chip ev-status-${e.status}`}>{STATUS_LABEL[e.status]}</span>}
          {e.role && <span className="chip chip-major">{ROLE_LABEL[e.role] ?? e.role}</span>}
          {e.geneva && <span className="chip chip-soft">Geneva</span>}
          {e.topics.slice(0, 3).map((t) => <span key={t} className="chip chip-topic">{t}</span>)}
          {e.clashes.length > 0 && <span className="chip chip-clash">⚠ Clash</span>}
        </div>
      </div>
    </button>
  );
}

function EventDrawer({ id, onClose, onChanged }: { id: number; onClose: () => void; onChanged: () => void }) {
  const [d, setD] = useState<EventDetail | null>(null);
  const load = useCallback(() => getEvent(id).then(setD).catch(() => setD(null)), [id]);
  useEffect(() => { load(); }, [load]);
  if (!d) return <Shell kicker="EVENT" title="Event" meta="" onClose={onClose}><p className="muted">Loading…</p></Shell>;
  const set = async (s: "interested" | "confirmed" | "declined" | null) => { await setEventStatus(id, s); await load(); onChanged(); };
  return (
    <Shell kicker={d.geneva ? "GENEVA" : "EVENT"} title={d.title} meta={when(d)} onClose={onClose} wide>
      <div className="ev-chips">
        {d.status === "confirmed" ? <span className="ev-badge">✓ You're in</span> : STATUS_LABEL[d.status] ? <span className={`chip ev-status-${d.status}`}>{STATUS_LABEL[d.status]}</span> : null}
        {d.role && <span className="chip chip-major">{ROLE_LABEL[d.role] ?? d.role}</span>}
        {d.topics.map((t) => <span key={t} className="chip chip-topic">{t}</span>)}
      </div>
      <div className="facts">
        {d.venue && <><span>Where</span><span>{d.venue}</span></>}
        {d.url && <><span>Link</span><span><a href={d.url} target="_blank" rel="noreferrer">{d.url.replace(/^https?:\/\//, "").slice(0, 60)}</a></span></>}
        <span>Status</span><span>{STATUS_LABEL[d.status] || "No response"}{d.overridden ? ` (you set this; your calendar says ${STATUS_LABEL[d.derived_status] || "nothing"})` : ""}</span>
      </div>
      {d.clashes.length > 0 && <div className="notice"><span>⚠ This clashes with another event you have confirmed or marked as maybe.</span></div>}
      <div className="stmt-actions">
        <button type="button" className={d.status === "confirmed" ? "btn-primary" : "btn-ghost"} onClick={() => set("confirmed")}>I'm going</button>
        <button type="button" className={d.status === "interested" ? "btn-primary" : "btn-ghost"} onClick={() => set("interested")}>Interested</button>
        <button type="button" className={d.status === "declined" ? "btn-primary" : "btn-ghost"} onClick={() => set("declined")}>Not going</button>
        {d.overridden && <button type="button" className="btn-ghost" onClick={() => set(null)}>Use my calendar's answer</button>}
        <button type="button" className="btn-ghost" onClick={async () => { await hideEvent(id); onChanged(); onClose(); }}>Not an event</button>
      </div>
      <div className="related"><div className="kicker">WHY IT IS HERE</div>
        {d.evidence.map((e, i) => <div key={i} className="related-row"><span>{e.kind === "calendar" ? "Your Google Calendar" : e.kind}: {e.signal ?? "—"}{e.detail ? ` · ${e.detail}` : ""}</span><span className="muted">{e.observed_at.slice(0, 10)}</span></div>)}
      </div>
    </Shell>
  );
}

export default function EventsTab() {
  const [scope, setScope] = useState<"upcoming" | "archive">("upcoming");
  const [q, setQ] = useState("");
  const [status, setStatus] = useState<string>("");
  const [geneva, setGeneva] = useState(false);
  const [topic, setTopic] = useState("");
  const [data, setData] = useState<EventsResponse | null>(null);
  const [open, setOpen] = useState<number | null>(null);
  const load = useCallback(() => getEvents({ scope, q: q || undefined, status: status || undefined, geneva: geneva || undefined, topic: topic || undefined }).then(setData).catch(() => setData(null)), [scope, q, status, geneva, topic]);
  useEffect(() => { const t = setTimeout(load, q ? 250 : 0); return () => clearTimeout(t); }, [load, q]);

  const groups: [string, EventItem[]][] = [];
  for (const e of data?.items ?? []) {
    const g = scope === "archive" ? new Intl.DateTimeFormat("en-GB", { month: "long", year: "numeric" }).format(new Date(e.start.slice(0, 10) + "T12:00:00")) : weekLabel(e.start);
    const last = groups[groups.length - 1];
    if (last && last[0] === g) last[1].push(e); else groups.push([g, [e]]);
  }
  const chip = (label: string, on: boolean, fn: () => void) => <button type="button" key={label} className={`ev-filter ${on ? "on" : ""}`} aria-pressed={on} onClick={fn}>{label}</button>;
  return (
    <main className="page ev-page">
      <div className="ev-head">
        <h2 className="serif">Geneva and beyond</h2>
        <div className="ev-seg" role="tablist" aria-label="Which events">
          {chip("Upcoming", scope === "upcoming", () => setScope("upcoming"))}{chip("Past year · archive", scope === "archive", () => setScope("archive"))}
        </div>
      </div>
      {scope === "upcoming" && data && <div className="ev-counts"><b>{data.counts.confirmed}</b> confirmed · <b>{data.counts.tentative}</b> maybe · <b>{data.counts.invited}</b> invited</div>}
      <div className="ev-filters">
        <input className="ev-search" value={q} onChange={(e) => setQ(e.target.value)} placeholder={scope === "archive" ? "Search the past year…" : "Search events…"} aria-label="Search events" />
        {chip("All", !status && !geneva && !topic, () => { setStatus(""); setGeneva(false); setTopic(""); })}
        {chip("Confirmed", status === "confirmed", () => setStatus(status === "confirmed" ? "" : "confirmed"))}
        {chip("Invited", status === "invited", () => setStatus(status === "invited" ? "" : "invited"))}
        {chip("Geneva", geneva, () => setGeneva(!geneva))}
        {(data?.topics ?? []).map((t) => chip(t, topic === t, () => setTopic(topic === t ? "" : t)))}
      </div>
      {data && data.items.length === 0 && <p className="muted">{scope === "upcoming" ? "No events match." : "Nothing in the archive matches."} Events come from your Google Calendar for now; invitations in your inbox and the public Geneva listings are the next steps.</p>}
      {groups.map(([g, items]) => <section key={g} className="ev-group"><h3 className="ev-week">{g}</h3>{items.map((e) => <Card key={e.id} e={e} onOpen={() => setOpen(e.id)} />)}</section>)}
      {data && data.total > data.items.length && <p className="muted">Showing the first {data.items.length} of {data.total}. Narrow the search to see the rest.</p>}
      {open !== null && <EventDrawer id={open} onClose={() => setOpen(null)} onChanged={load} />}
    </main>
  );
}
