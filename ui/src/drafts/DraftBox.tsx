import { useEffect, useRef, useState } from "react";
import { type Draft, type DraftOpts, approveDraft, cancelDraft, getAgent, getDraft } from "../api";

const TONES: [string, string][] = [["", "learned / professional"], ["professional", "professional"], ["formal", "formal"], ["warm", "warm"], ["brief", "brief"]];
const LANGS: [string, string][] = [["", "auto"], ["en", "English"], ["fr", "French"], ["de", "German"], ["it", "Italian"], ["es", "Spanish"]];
const LANG_NAME: Record<string, string> = { en: "English", fr: "French", de: "German", it: "Italian", es: "Spanish" };

function whyLine(d: Draft): string {
  const p = d.profile, lang = LANG_NAME[d.language ?? ""] ?? d.language ?? "";
  if (p.overridden?.tone || p.overridden?.language) {
    return `${lang} · ${d.tone} · as you asked${p.default_used ? "" : ", with your usual greeting and closing for this person"}`;
  }
  if (p.default_used) return `${lang} · professional tone: I have no history of how you write to this person. Change the tone below if you like.`;
  return `${lang} · ${p.pronoun ? p.pronoun + " · " : ""}${d.tone}: learned from ${p.n_mine ?? 0} of your messages (${p.source === "edited" ? "as you corrected it" : p.confidence + " confidence"})`;
}

/** The draft editor: generate, edit, then "Save to Gmail". Gmail is only touched after the Save click. */
export default function DraftBox({ initial, generate, startLabel = "Draft a reply", followUp = false, children }: {
  initial: Draft | null; generate: (o: DraftOpts) => Promise<Draft>; startLabel?: string; followUp?: boolean; children?: React.ReactNode;
}) {
  const [draft, setDraft] = useState<Draft | null>(initial && initial.status !== "cancelled" ? initial : null);
  const [tone, setTone] = useState(""); const [lang, setLang] = useState(""); const [note, setNote] = useState("");
  const [showOpts, setShowOpts] = useState(false);
  const [busy, setBusy] = useState(false); const [err, setErr] = useState("");
  const [subject, setSubject] = useState(draft?.subject ?? ""); const [body, setBody] = useState(draft?.body ?? "");
  const [to, setTo] = useState((draft?.to ?? []).join(", "));
  const [agentOk, setAgentOk] = useState<boolean | null>(null);
  const poll = useRef<number>();

  const load = (d: Draft) => { setDraft(d); setSubject(d.subject); setBody(d.body); setTo(d.to.join(", ")); };
  useEffect(() => { if (initial && initial.status !== "cancelled") load(initial); }, [initial?.id]);   // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => () => window.clearInterval(poll.current), []);
  useEffect(() => {      // after "Save to Gmail", wait for the Mac-side agent
    window.clearInterval(poll.current);
    if (draft?.status === "approved") {
      getAgent().then((a) => setAgentOk(a.alive)).catch(() => undefined);
      poll.current = window.setInterval(async () => {
        const d = await getDraft(draft.id).catch(() => null);
        if (d && d.status !== "approved") { setDraft(d); window.clearInterval(poll.current); }
        else getAgent().then((a) => setAgentOk(a.alive)).catch(() => undefined);
      }, 2000);
    }
  }, [draft?.status, draft?.id]);

  const run = async () => {
    setBusy(true); setErr("");
    try { load(await generate({ tone: tone || null, language: lang || null, instruction: note.trim() || null })); setShowOpts(false); }
    catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
  };
  const save = async () => {
    if (!draft) return;
    setBusy(true); setErr("");
    try { setDraft(await approveDraft(draft.id, { body, subject, to: to.split(/[,;\s]+/).filter(Boolean), cc: draft.cc })); }
    catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
  };
  const discard = async () => { if (draft) await cancelDraft(draft.id); setDraft(null); setShowOpts(false); };

  const opts = (
    <div className="draft-opts">
      <label>Tone<select value={tone} onChange={(e) => setTone(e.target.value)}>{TONES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select></label>
      <label>Language<select value={lang} onChange={(e) => setLang(e.target.value)}>{LANGS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select></label>
      <label className="wide">What should it say? <small>(optional)</small><input value={note} onChange={(e) => setNote(e.target.value)} maxLength={500} placeholder="e.g. accept, but ask for the agenda first" /></label>
      {children}
    </div>
  );

  if (!draft) {
    return (
      <div className="draft-box">
        <div className="kicker">{followUp ? "FOLLOW-UP" : "DRAFT"}</div>
        {followUp && <div className="why">You wrote last in this conversation, so this will be a follow-up to the person you wrote to. Tell it what to say below, for example “ask whether they received it”.</div>}
        {showOpts ? <>{opts}<div className="editor-actions"><button type="button" className="btn-small" onClick={run} disabled={busy}>{busy ? "Writing… (up to a minute)" : "Write the draft"}</button><button type="button" className="btn-ghost" onClick={() => setShowOpts(false)}>Cancel</button></div></>
          : <div className="editor-actions"><button type="button" className="btn-small" onClick={run} disabled={busy}>{busy ? "Writing… (up to a minute)" : startLabel}</button>
              <button type="button" className="link-quiet" onClick={() => setShowOpts(true)}>Choose tone, language or what to say first</button></div>}
        {err && <div className="edit-err">{err}</div>}
        <div className="note">Written on this Mac only. Nothing goes to Gmail until you click Save. You send it yourself from Gmail.</div>
      </div>
    );
  }

  if (draft.status === "created") {
    return (
      <div className="draft-box done">
        <div className="added">✓ Saved in your Gmail Drafts{draft.in_thread ? " (in the conversation)" : ""}. Review it there and send it yourself.</div>
        <a className="btn-primary link-btn" href="https://mail.google.com/mail/u/0/#drafts" target="_blank" rel="noreferrer">Open Gmail drafts</a>
        <button type="button" className="link-quiet" onClick={() => setDraft(null)}>Write another version</button>
      </div>
    );
  }

  const locked = draft.status === "approved";
  return (
    <div className="draft-box">
      <div className="kicker">{draft.follow_up ? "FOLLOW-UP" : "DRAFT"} · {draft.model}</div>
      {draft.follow_up && <div className="why">You wrote last in this conversation. This follows up with the people your message went to. Check the To box.</div>}
      <div className="why">{whyLine(draft)}</div>
      {draft.needs_input.length > 0 && <div className="needs-input"><b>Fill in before sending:</b> {draft.needs_input.join(" · ")}</div>}
      {draft.placeholders > 0 && <div className="needs-input">The text still contains [YOUR INPUT …] markers. You can save it and complete it in Gmail, but check it before you send.</div>}
      <label className="f">To<input value={to} onChange={(e) => setTo(e.target.value)} disabled={locked} /></label>
      <label className="f">Subject<input value={subject} onChange={(e) => setSubject(e.target.value)} disabled={locked} maxLength={300} /></label>
      <label className="f">Message<textarea rows={12} value={body} onChange={(e) => setBody(e.target.value)} disabled={locked} /></label>
      {draft.status === "failed" && <div className="edit-err">Could not save to Gmail: {draft.error}</div>}
      {locked && <div className="notice">Waiting for the draft agent to save it to Gmail…{agentOk === false && <> <b>The agent does not seem to be running.</b> On your Mac run <span className="mono">make agent-install</span> (or <span className="mono">make agent-status</span> to check).</>}</div>}
      {err && <div className="edit-err">{err}</div>}
      {!locked && <>
        {showOpts && <>{opts}<div className="editor-actions"><button type="button" className="btn-small" onClick={run} disabled={busy}>{busy ? "Writing…" : "Write it again"}</button><button type="button" className="btn-ghost" onClick={() => setShowOpts(false)}>Cancel</button></div></>}
        <div className="editor-actions">
          <button type="button" className="btn-done" onClick={save} disabled={busy || !body.trim()}>Save to Gmail as a draft</button>
          {!showOpts && <button type="button" className="btn-ghost" onClick={() => setShowOpts(true)}>Change and rewrite…</button>}
          <button type="button" className="btn-ghost" onClick={discard}>Discard</button>
        </div>
        <div className="note">Saving creates a draft in Gmail with exactly this text. Nothing is sent: you review and send it yourself.</div>
      </>}
    </div>
  );
}
