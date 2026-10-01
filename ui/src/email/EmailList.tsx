import { useCallback, useEffect, useRef, useState } from "react";
import { type Email, type EmailsResponse, type TriageStatus, emailToTask, getEmails, getTriageStatus, labelEmail, runTriage } from "../api";
import { Shell } from "../today/Drawer";
import { dayMonth, dayShort, timeOf } from "../format";

const RANGES = [24, 48, 72];
const initials = (n: string) => n.split(/[\s@.]+/).filter(Boolean).slice(0, 2).map((x) => x[0]?.toUpperCase()).join("");
const ago = (h: number) => (h < 1 ? "<1 h" : h < 48 ? `${Math.round(h)} h` : `${Math.round(h / 24)} d`);

function EmailDrawer({ e, onClose, onChanged }: { e: Email; onClose: () => void; onChanged: () => void }) {
  const [label, setLabel] = useState(e.user_label);
  const [taskId, setTaskId] = useState(e.task_id);
  const [busy, setBusy] = useState(false);
  const pick = async (v: "yes" | "no") => { const next = label === v ? null : v; setLabel(next); await labelEmail(e.id, next); onChanged(); };
  const addTask = async () => { setBusy(true); try { const r = await emailToTask(e.id); setTaskId(r.task_id); onChanged(); } finally { setBusy(false); } };
  const facts: [string, string][] = [
    ["From", `${e.from_name} <${e.from_email}>`],
    ...(e.known ? ([["Known as", [e.role, e.org].filter(Boolean).join(", ") || "in your People list"]] as [string, string][]) : []),
    ["Received", `${dayShort(e.received_at)} · ${timeOf(e.received_at)}`],
    ["Addressed", e.direct ? "to you directly" : "you are copied"],
    ["What", e.action ?? "—"],
    ...(e.deadline ? ([["Deadline", dayShort(e.deadline)]] as [string, string][]) : []),
    ["Why", e.why ?? "—"],
    ["Urgency", e.urgency === 3 ? "time pressure" : e.urgency === 2 ? "soon" : "ordinary"],
  ];
  return (
    <Shell kicker={`EMAIL${e.org ? " · " + e.org.toUpperCase() : ""}`} title={e.subject} meta={`${e.from_name} · ${Math.round(e.hours_ago)} h ago`} onClose={onClose}>
      <div className="facts">{facts.map(([k, v]) => <><span key={k + "k"}>{k}</span><span key={k + "v"}>{v}</span></>)}</div>
      {e.snippet && <div className="related"><div className="kicker">PREVIEW</div><div className="preview">{e.snippet}</div></div>}
      <div className="actions">
        {taskId
          ? <div className="added">✓ In Today &amp; overdue{e.deadline ? ` (due ${dayMonth(e.deadline)})` : " (due today)"}</div>
          : <button type="button" className="btn-primary" disabled={busy} onClick={addTask}>Add to Today &amp; overdue{e.deadline ? ` · due ${dayMonth(e.deadline)}` : ""}</button>}
      </div>
      <div className="feedback">
        <div className="kicker">TEACH THE HARNESS</div>
        <div className="fb-row">
          <button type="button" className={label === "yes" ? "on-yes" : ""} onClick={() => pick("yes")}>This needs me</button>
          <button type="button" className={label === "no" ? "on-no" : ""} onClick={() => pick("no")}>This doesn't need me</button>
        </div>
        <div className="note">Your verdicts are saved here only. They are used to score the models, and never leave this Mac.</div>
      </div>
      <a className="btn-primary link-btn" href={`https://mail.google.com/mail/u/0/#inbox/${e.thread_id}`} target="_blank" rel="noreferrer">Open in Gmail</a>
      <div className="note">Suggested replies arrive in Phase 3. The harness will only ever create drafts; it can't send.</div>
    </Shell>
  );
}

function Row({ e, onOpen, dim }: { e: Email; onOpen: (e: Email) => void; dim?: boolean }) {
  return (
    <button type="button" className={`row-btn ${dim ? "dim" : ""}`} onClick={() => onOpen(e)}>
      <div className="avatar">{initials(e.from_name)}</div>
      <div className="row-main">
        <div className="row-subject">{e.subject}</div>
        <div className="row-sub"><span>{e.from_name}</span>{e.why && <span className={`why ${e.urgency === 3 ? "why-urgent" : ""}`}>{e.why}</span>}
          {e.deadline && <span className="why why-urgent">by {dayMonth(e.deadline)}</span>}
          {e.user_label && <span className="mark-label">{e.user_label === "yes" ? "✓ you: needs me" : "✕ you: doesn't"}</span>}</div>
      </div>
      <span className="ago">{ago(e.hours_ago)}</span>
    </button>
  );
}

/** The email list used on Today (needs-reply only) and on the Inbox tab (also what was skipped). */
export default function EmailList({ full }: { full: boolean }) {
  const [hours, setHours] = useState(72);
  const [data, setData] = useState<EmailsResponse | null>(null);
  const [status, setStatus] = useState<TriageStatus | null>(null);
  const [open, setOpen] = useState<Email | null>(null);
  const [error, setError] = useState(false);
  const poll = useRef<number>();

  const load = useCallback(() => getEmails(hours, full).then((d) => { setData(d); setError(false); }).catch(() => setError(true)), [hours, full]);
  useEffect(() => { load(); }, [load]);
  useEffect(() => () => window.clearInterval(poll.current), []);

  const triage = async () => {
    setStatus(await runTriage());
    window.clearInterval(poll.current);
    poll.current = window.setInterval(async () => {
      const s = await getTriageStatus();
      setStatus(s); load();
      if (!s.running) window.clearInterval(poll.current);
    }, 4000);
  };

  if (error) return <div className="placeholder"><b>Couldn't load emails</b><span>The back end isn't answering. Is it running (make up)?</span></div>;
  if (!data) return <p className="muted">Loading…</p>;
  const c = data.counts;
  const total = c.pending + c.skipped + c.done + c.error;
  const running = status?.running;

  return (
    <>
      <div className="range" role="group" aria-label="Time window">
        {RANGES.map((r) => <button key={r} type="button" aria-pressed={r === hours} className={r === hours ? "on" : ""} onClick={() => setHours(r)}>{r} h</button>)}
      </div>
      <div className="sub">
        {total === 0
          ? "No emails loaded yet."
          : `${data.needs_reply.length} need a reply in the last ${hours} hours · ${c.skipped} skipped (newsletters, automated, already answered)`}
      </div>

      {total === 0 && <div className="placeholder"><b>Nothing fetched from Gmail yet</b><span>On your Mac, run <span className="mono">make gmail</span> in the ig-harness folder. It reads your recent inbox (read-only) and then triages it.</span></div>}

      {(c.pending > 0 || c.error > 0) && (
        <div className="notice">
          <span>{running ? "Reading your emails with the local model…" : `${c.pending} email${c.pending === 1 ? "" : "s"} waiting to be triaged${c.error ? `, ${c.error} to retry` : ""}.`}</span>
          <button type="button" onClick={triage} disabled={running}>{running ? "Working…" : "Triage now"}</button>
        </div>
      )}

      {data.needs_reply.map((e) => <Row key={e.id} e={e} onOpen={setOpen} />)}
      {total > 0 && c.pending === 0 && data.needs_reply.length === 0 && <div className="empty">Nothing needs a reply in this window.</div>}

      {full && (data.not_needing_reply?.length ?? 0) > 0 && (
        <details className="skipped">
          <summary>Not needing a reply ({data.not_needing_reply!.length})</summary>
          {data.not_needing_reply!.map((e) => <Row key={e.id} e={e} onOpen={setOpen} dim />)}
        </details>
      )}
      {open && <EmailDrawer e={open} onClose={() => { setOpen(null); load(); }} onChanged={load} />}
    </>
  );
}
