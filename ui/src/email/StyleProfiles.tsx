import { useCallback, useEffect, useState } from "react";
import { type Profile, type Signature, getProfiles, getSignature, patchProfile, putSignature, relearnProfile } from "../api";

const LANGS: Record<string, string> = { en: "English", fr: "French", de: "German", it: "Italian", es: "Spanish" };
const DOTS = { none: 0, low: 1, medium: 2, high: 3 } as const;

function Editor({ p, onDone }: { p: Profile; onDone: () => void }) {
  const [f, setF] = useState({ language: p.language ?? "", formality: p.formality ?? "", pronoun: p.pronoun ?? "", greeting: p.greeting ?? "", closing: p.closing ?? "", notes: p.notes ?? "" });
  const [err, setErr] = useState("");
  const save = async () => {
    try {
      await patchProfile(p.person_email, { language: f.language || null, formality: (f.formality || null) as Profile["formality"], pronoun: f.pronoun || null, greeting: f.greeting || null, closing: f.closing || null, notes: f.notes || null });
      onDone();
    } catch (e) { setErr((e as Error).message); }
  };
  const set = (k: keyof typeof f) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => setF({ ...f, [k]: e.target.value });
  return (
    <div className="prof-edit">
      <div className="prof-grid">
        <label>Language<select value={f.language} onChange={set("language")}><option value="">not sure</option>{Object.entries(LANGS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></label>
        <label>Tone<select value={f.formality} onChange={set("formality")}><option value="">professional (default)</option><option value="formal">formal</option><option value="informal">informal</option><option value="neutral">neutral</option></select></label>
        <label>"You" form<select value={f.pronoun} onChange={set("pronoun")}><option value="">n/a</option><option value="vous">vous</option><option value="tu">tu</option><option value="Sie">Sie</option><option value="du">du</option></select></label>
      </div>
      <label>Usual greeting <small>({"{name}"} = their name)</small><input value={f.greeting} onChange={set("greeting")} maxLength={120} placeholder="e.g. Dear {name}," /></label>
      <label>Usual closing<input value={f.closing} onChange={set("closing")} maxLength={80} placeholder="e.g. Kind regards," /></label>
      <label>Note to yourself<input value={f.notes} onChange={set("notes")} maxLength={300} placeholder="e.g. keep it short; he prefers bullet points" /></label>
      {err && <div className="edit-err">{err}</div>}
      <div className="editor-actions">
        <button type="button" className="btn-small" onClick={save}>Save</button>
        <button type="button" className="btn-ghost" onClick={onDone}>Cancel</button>
        {p.source === "edited" && <button type="button" className="btn-ghost" onClick={async () => { await relearnProfile(p.person_email); onDone(); }}>Reset to what I learned</button>}
      </div>
    </div>
  );
}

export default function StyleProfiles() {
  const [items, setItems] = useState<Profile[] | null>(null);
  const [sig, setSig] = useState<Signature | null>(null);
  const [sigText, setSigText] = useState("");
  const [open, setOpen] = useState<string | null>(null);
  const [q, setQ] = useState("");
  const [saved, setSaved] = useState("");
  const load = useCallback(() => {
    getProfiles().then((r) => setItems(r.items)).catch(() => setItems([]));
    getSignature().then((s) => { setSig(s); setSigText(s.signature); }).catch(() => undefined);
  }, []);
  useEffect(() => { load(); }, [load]);

  const shown = (items ?? []).filter((p) => !q || `${p.name ?? ""} ${p.person_email} ${p.org ?? ""}`.toLowerCase().includes(q.toLowerCase()));
  return (
    <section className="card-box" aria-label="How you write to people">
      <h3>How you write to people</h3>
      <div className="note">Learned from your past emails with each person (read-only; it stays on this Mac). Draft replies use this. Correct anything that is wrong: your corrections are never overwritten.</div>

      <div className="sig-box">
        <div className="kicker">YOUR SIGNATURE</div>
        <textarea rows={4} value={sigText} onChange={(e) => setSigText(e.target.value)} placeholder="Your signature, added under each draft" maxLength={600} />
        <div className="editor-actions">
          <button type="button" className="btn-small" disabled={sigText.trim() === (sig?.signature ?? "")} onClick={async () => { await putSignature(sigText); setSaved("Signature saved."); load(); }}>Save signature</button>
          {sig?.learned && sig.learned !== sigText && <button type="button" className="btn-ghost" onClick={() => setSigText(sig.learned!)}>Use the one I found in your emails</button>}
          {saved && <span className="note">{saved}</span>}
        </div>
      </div>

      {items && items.length === 0 && <div className="placeholder"><b>No profiles yet</b><span>On your Mac, run <span className="mono">make correspondence</span> in the ig-harness folder. It reads your recent emails with each person (read-only) and learns how you write to them.</span></div>}
      {items && items.length > 0 && <input className="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder={`Search ${items.length} people…`} aria-label="Search people" />}
      {shown.map((p) => (
        <div key={p.person_email} className={`prof ${open === p.person_email ? "open" : ""}`}>
          <button type="button" className="prof-head" onClick={() => setOpen(open === p.person_email ? null : p.person_email)} aria-expanded={open === p.person_email}>
            <span className="prof-name">{p.name ?? p.person_email}{p.source === "edited" && <em> · edited by you</em>}</span>
            <span className="prof-tags">
              {p.language && <span className="chip chip-soft">{LANGS[p.language] ?? p.language}</span>}
              {p.formality && p.formality !== "neutral" && <span className={`chip ${p.formality === "formal" ? "chip-hard" : "chip-personal"}`}>{p.pronoun ?? p.formality}</span>}
              <span className="dots" title={`${p.n_mine} of your messages, ${p.n_threads} conversations`}>{"●".repeat(DOTS[p.confidence])}{"○".repeat(3 - DOTS[p.confidence])}</span>
            </span>
            <span className="prof-line muted small">
              {p.n_mine === 0 ? (p.n_theirs ? "You have not written to them in what I read: professional tone by default" : "No history: professional tone by default")
                : <>{p.greeting ?? "no usual greeting"} → {p.closing ?? "no usual closing"} · {p.n_mine} message{p.n_mine === 1 ? "" : "s"}{p.avg_words ? `, about ${p.avg_words} words` : ""}</>}
            </span>
          </button>
          {open === p.person_email && <Editor p={p} onDone={() => { setOpen(null); load(); }} />}
        </div>
      ))}
    </section>
  );
}
