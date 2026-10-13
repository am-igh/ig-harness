import { useEffect, useState } from "react";
import { type OnbOptions, type OnbPreview, createOnb, getMeta, getOnbOptions, previewOnb } from "../api";
import { dateY, money } from "./fmt";

type Rep = { canon: string; title: string; recurrence: string; anchor: string; offset_days: number; fixed_date: string; language: string; format: string; detail: string; clause: string; note: string };
type Pay = { label: string; expected_date: string; expected_amount: string; condition: string };
type Contact = { name: string; role: string; email: string; phone: string };
type S = {
  pmode: "existing" | "new"; pid: number; pcode: string; pname: string; plead: string;
  fmode: "existing" | "new"; fid: number; fname: string; fshort: string; frole: string; fcur: string;
  title: string; kind: string; reference: string; signed: string; start: string; end: string; amount: string; cur: string; rate: string; path: string; summary: string;
  payments: Pay[]; reports: Rep[];
  overhead: string; overheadClause: string; approval: string; threshold: string; quotes: string; visibility: string; eligible: string;
  notice: string; law: string; ownership: string; data: string; special: string; contacts: Contact[];
};
const blank: S = {
  pmode: "new", pid: 0, pcode: "", pname: "", plead: "", fmode: "new", fid: 0, fname: "", fshort: "", frole: "funder", fcur: "CHF",
  title: "Grant agreement", kind: "grant", reference: "", signed: "", start: "", end: "", amount: "", cur: "CHF", rate: "", path: "", summary: "",
  payments: [], reports: [], overhead: "", overheadClause: "", approval: "", threshold: "", quotes: "3", visibility: "", eligible: "",
  notice: "", law: "", ownership: "", data: "", special: "", contacts: [],
};
const STEPS = ["Parties", "Money", "Reports and deadlines", "Other terms", "Review"];
const REC: Record<string, string> = { once: "Once", quarterly: "Every quarter", semiannual: "Every six months", annual: "Every year" };
const ANCHOR: Record<string, string> = { period_end: "after each period ends", end: "after the contract ends", start: "after the contract starts", fixed: "on a fixed date" };

const EXAMPLE: S = {
  ...blank, pcode: "PEACEFUL", pname: "Peaceful Futures (example)", plead: "Programme lead", fname: "Example Foundation", fshort: "EXF", fcur: "EUR",
  title: "Grant agreement", reference: "EXF/2026/014", signed: "2026-01-15", start: "2026-02-01", end: "2028-01-31", amount: "240000", cur: "EUR", rate: "0.94", path: "Contracts/Example Foundation/grant-agreement.pdf", summary: "Two-year grant for community dialogue work.",
  payments: [{ label: "First instalment", expected_date: "2026-02-15", expected_amount: "120000", condition: "On signature" }, { label: "Second instalment", expected_date: "2027-03-01", expected_amount: "120000", condition: "After the first annual report is accepted" }],
  reports: [
    { canon: "financial_report", title: "Quarterly financial report", recurrence: "quarterly", anchor: "period_end", offset_days: 30, fixed_date: "", language: "en", format: "Funder workbook", detail: "detailed", clause: "5.1", note: "" },
    { canon: "narrative_report", title: "Annual narrative report", recurrence: "annual", anchor: "period_end", offset_days: 60, fixed_date: "", language: "en", format: "Funder template", detail: "standard", clause: "5.2", note: "" },
    { canon: "audit", title: "External audit", recurrence: "once", anchor: "end", offset_days: 120, fixed_date: "", language: "en", format: "", detail: "line-by-line", clause: "7", note: "" },
  ],
  overhead: "7", overheadClause: "6.4", approval: "10", threshold: "5000", quotes: "3", visibility: "Acknowledge the funder in all public outputs", eligible: "Costs incurred in the contract period and necessary for the project",
  notice: "90", law: "Swiss law, Geneva courts", ownership: "Outputs belong to the grantee; the funder may share them with credit", data: "Personal data stays in Switzerland", special: "Prior written approval to subcontract",
  contacts: [{ name: "Programme officer (example)", role: "Programme officer", email: "officer@example.org", phone: "" }],
};

function toPayload(s: S) {
  return {
    project: s.pmode === "existing" ? { mode: "existing", id: s.pid } : { mode: "new", code: s.pcode, name: s.pname, lead: s.plead, start_date: s.start || null, end_date: s.end || null },
    funder: s.fmode === "existing" ? { mode: "existing", id: s.fid } : { mode: "new", name: s.fname, short: s.fshort, role: s.frole, currency: s.fcur, contact: s.contacts[0]?.name || "" },
    contract: { title: s.title, kind: s.kind, reference: s.reference, signed_date: s.signed || null, start_date: s.start || null, end_date: s.end || null, amount: s.amount, currency: s.cur, budget_rate: s.rate, file_path: s.path, summary: s.summary },
    payments: s.payments, reports: s.reports.map((r) => ({ ...r, fixed_date: r.fixed_date || null })),
    rules: { overhead_pct: s.overhead, overhead_clause: s.overheadClause, approval_pct: s.approval, procurement_threshold: s.threshold, procurement_quotes: s.quotes, visibility: s.visibility, eligible_costs: s.eligible },
    terms: { termination_notice_days: s.notice, governing_law: s.law, ownership: s.ownership, data_protection: s.data, special_conditions: s.special, contacts: s.contacts.filter((c) => c.name.trim()) },
  };
}

const F = ({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) => <label className="onb-f"><span>{label}</span>{children}{hint && <em className="small muted">{hint}</em>}</label>;

/** Contract onboarding: one guided form that collects everything a contract can require, then shows what will be created before anything is saved. */
export default function OnboardWizard({ onDone, onCancel }: { onDone: (projectId: number) => void; onCancel: () => void }) {
  const [o, setO] = useState<OnbOptions | null>(null);
  const [s, setS] = useState<S>(blank);
  const [step, setStep] = useState(0);
  const [pv, setPv] = useState<OnbPreview | null>(null);
  const [err, setErr] = useState(""); const [busy, setBusy] = useState(false); const [demo, setDemo] = useState(false);
  useEffect(() => { getOnbOptions().then((x) => { setO(x); setS((p) => ({ ...p, pmode: x.projects.length ? "existing" : "new", pid: x.projects[0]?.id ?? 0, fmode: x.funders.length ? "existing" : "new", fid: x.funders[0]?.id ?? 0 })); }).catch((e) => setErr(e.message)); getMeta().then((m) => setDemo(m.demo)).catch(() => {}); }, []);
  const set = <K extends keyof S>(k: K, v: S[K]) => setS((p) => ({ ...p, [k]: v }));
  const text = (k: keyof S, ph?: string) => <input value={String(s[k])} onChange={(e) => set(k, e.target.value as never)} placeholder={ph} />;
  const area = (k: keyof S, ph?: string) => <textarea rows={2} value={String(s[k])} onChange={(e) => set(k, e.target.value as never)} placeholder={ph} />;
  const funderCur = s.fmode === "existing" ? o?.funders.find((f) => f.id === s.fid)?.currency : s.fcur;
  const pickFunder = (id: number) => { const f = o?.funders.find((x) => x.id === id); setS((p) => ({ ...p, fid: id, cur: f?.currency ?? p.cur })); };
  const addPreset = (id: string) => { const p = o?.presets.find((x) => x.id === id); if (p) set("reports", [...s.reports, { canon: p.canon, title: p.label, recurrence: p.recurrence, anchor: p.anchor, offset_days: p.offset_days, fixed_date: "", language: "", format: "", detail: p.detail, clause: "", note: "" }]); };
  const setRep = (i: number, patch: Partial<Rep>) => set("reports", s.reports.map((r, k) => (k === i ? { ...r, ...patch } : r)));
  const setPay = (i: number, patch: Partial<Pay>) => set("payments", s.payments.map((r, k) => (k === i ? { ...r, ...patch } : r)));
  const setCon = (i: number, patch: Partial<Contact>) => set("contacts", s.contacts.map((r, k) => (k === i ? { ...r, ...patch } : r)));
  const sum = s.payments.reduce((a, p) => a + (Number(p.expected_amount) || 0), 0);

  const go = async (n: number) => {
    setErr("");
    if (n === 4) { setBusy(true); try { setPv(await previewOnb(toPayload(s))); } catch (e) { setErr((e as Error).message); setBusy(false); return; } setBusy(false); }
    setStep(n);
  };
  const create = async () => { setBusy(true); setErr(""); try { const r = await createOnb(toPayload(s)); onDone(r.project_id); } catch (e) { setErr((e as Error).message); setBusy(false); } };

  return (
    <div className="onb">
      <div className="panel-head"><h2 className="serif">Add a contract</h2><span>{demo && step === 0 && <button type="button" className="btn-ghost" onClick={() => setS({ ...EXAMPLE, pmode: "new", fmode: "new" })}>Fill with an example</button>} <button type="button" className="btn-ghost" onClick={onCancel}>Cancel</button></span></div>
      <div className="sub">Collect everything the contract says in one place. Nothing is saved until the last step, where you can see exactly what will be created. The signed contract itself stays in your folders.</div>
      <ol className="onb-steps" aria-label="Steps">{STEPS.map((t, i) => <li key={t} className={i === step ? "on" : i < step ? "done" : ""}><button type="button" onClick={() => (i < step ? setStep(i) : undefined)} disabled={i >= step}>{i + 1}. {t}</button></li>)}</ol>

      {step === 0 && <section className="onb-card">
        <h3 className="serif">The project</h3>
        <div className="onb-row"><label><input type="radio" checked={s.pmode === "existing"} disabled={!o?.projects.length} onChange={() => set("pmode", "existing")} /> An existing project</label><label><input type="radio" checked={s.pmode === "new"} onChange={() => set("pmode", "new")} /> A new project</label></div>
        {s.pmode === "existing" ? <F label="Project"><select value={s.pid} onChange={(e) => set("pid", Number(e.target.value))}>{o?.projects.map((p) => <option key={p.id} value={p.id}>{p.code} · {p.name}</option>)}</select></F> : <div className="onb-grid"><F label="Project code" hint="Short, e.g. AURORA"><input value={s.pcode} maxLength={10} onChange={(e) => set("pcode", e.target.value.toUpperCase())} /></F><F label="Project name">{text("pname")}</F><F label="Project lead">{text("plead")}</F></div>}
        <h3 className="serif">The funder or partner</h3>
        <div className="onb-row"><label><input type="radio" checked={s.fmode === "existing"} disabled={!o?.funders.length} onChange={() => set("fmode", "existing")} /> Already in the list</label><label><input type="radio" checked={s.fmode === "new"} onChange={() => set("fmode", "new")} /> A new one</label></div>
        {s.fmode === "existing" ? <F label="Funder or partner"><select value={s.fid} onChange={(e) => pickFunder(Number(e.target.value))}>{o?.funders.map((f) => <option key={f.id} value={f.id}>{f.short} · {f.name} ({f.currency})</option>)}</select></F> : <div className="onb-grid"><F label="Name">{text("fname")}</F><F label="Short name">{text("fshort")}</F><F label="Currency of the contract"><input value={s.fcur} maxLength={3} onChange={(e) => { set("fcur", e.target.value.toUpperCase()); set("cur", e.target.value.toUpperCase()); }} /></F><F label="Role"><select value={s.frole} onChange={(e) => set("frole", e.target.value)}><option value="funder">Funder</option><option value="partner">Partner</option></select></F></div>}
        <h3 className="serif">The contract</h3>
        <div className="onb-grid"><F label="Title">{text("title")}</F><F label="Kind"><select value={s.kind} onChange={(e) => set("kind", e.target.value)}><option value="grant">Grant (money comes in)</option><option value="subgrant">Sub-grant (money goes out)</option></select></F><F label="Reference number" hint="The funder's own number">{text("reference")}</F></div>
        <div className="onb-grid"><F label="Signed on"><input type="date" value={s.signed} onChange={(e) => set("signed", e.target.value)} /></F><F label="Starts"><input type="date" value={s.start} onChange={(e) => set("start", e.target.value)} /></F><F label="Ends"><input type="date" value={s.end} onChange={(e) => set("end", e.target.value)} /></F></div>
        <F label="Where the signed contract is kept" hint="A path in your own folders; the harness keeps only the location">{text("path")}</F>
        <F label="In a sentence, what is it for?">{area("summary")}</F>
      </section>}

      {step === 1 && <section className="onb-card">
        <h3 className="serif">Amount</h3>
        <div className="onb-grid"><F label="Contract amount"><input inputMode="decimal" value={s.amount} onChange={(e) => set("amount", e.target.value)} /></F><F label="Currency"><input value={s.cur} maxLength={3} onChange={(e) => set("cur", e.target.value.toUpperCase())} /></F>{s.cur !== "CHF" && <F label={`Budget rate (CHF per 1 ${s.cur || "unit"})`} hint="The rate the contract budget assumes"><input inputMode="decimal" value={s.rate} onChange={(e) => set("rate", e.target.value)} /></F>}</div>
        <h3 className="serif">{s.kind === "grant" ? "When the money is due" : "Payment schedule"}</h3>
        {s.kind === "subgrant" && <p className="small muted">For a sub-grant the money goes out, so no expected income is recorded.</p>}
        {s.payments.map((p, i) => <div key={i} className="onb-line"><input placeholder="Label, e.g. First instalment" value={p.label} onChange={(e) => setPay(i, { label: e.target.value })} /><input type="date" value={p.expected_date} onChange={(e) => setPay(i, { expected_date: e.target.value })} /><input inputMode="decimal" placeholder={`Amount (${s.cur})`} value={p.expected_amount} onChange={(e) => setPay(i, { expected_amount: e.target.value })} /><input placeholder="Condition, if any" value={p.condition} onChange={(e) => setPay(i, { condition: e.target.value })} /><button type="button" className="btn-ghost" onClick={() => set("payments", s.payments.filter((_, k) => k !== i))} aria-label="Remove this payment">✕</button></div>)}
        <div className="onb-row"><button type="button" className="btn-ghost" onClick={() => set("payments", [...s.payments, { label: `Instalment ${s.payments.length + 1}`, expected_date: "", expected_amount: "", condition: "" }])}>+ Add a payment</button>{s.payments.length > 0 && <span className="small muted">Payments add up to {money(sum, s.cur)}{s.amount ? ` of ${money(Number(s.amount), s.cur)}` : ""}</span>}</div>
        <h3 className="serif">Money rules in the contract</h3>
        <div className="onb-grid"><F label="Overhead cap (%)"><input inputMode="decimal" value={s.overhead} onChange={(e) => set("overhead", e.target.value)} /></F><F label="Clause"><input value={s.overheadClause} onChange={(e) => set("overheadClause", e.target.value)} /></F><F label="Prior approval for moving money between budget lines above (%)"><input inputMode="decimal" value={s.approval} onChange={(e) => set("approval", e.target.value)} /></F></div>
        <div className="onb-grid"><F label={`Procurement: quotes needed above (${s.cur})`}><input inputMode="decimal" value={s.threshold} onChange={(e) => set("threshold", e.target.value)} /></F><F label="Number of quotes"><input inputMode="numeric" value={s.quotes} onChange={(e) => set("quotes", e.target.value)} /></F></div>
        <F label="What costs are eligible?">{area("eligible")}</F>
      </section>}

      {step === 2 && <section className="onb-card">
        <h3 className="serif">Reports and deadlines</h3>
        <p className="small muted">Pick what the contract asks for; the harness works out every due date from the contract dates. You can change any line.</p>
        <div className="onb-presets">{o?.presets.map((p) => <button key={p.id} type="button" className="btn-ghost" onClick={() => addPreset(p.id)}>+ {p.label}</button>)}</div>
        {s.reports.length === 0 && <p className="muted">Nothing added yet. Click one of the buttons above, or add a custom requirement.</p>}
        {s.reports.map((r, i) => <div key={i} className="onb-rep">
          <div className="onb-line"><input value={r.title} onChange={(e) => setRep(i, { title: e.target.value })} aria-label="Title" /><select value={r.canon} onChange={(e) => setRep(i, { canon: e.target.value })} aria-label="Kind of requirement">{o && Object.entries(o.canon).filter(([k]) => !["visibility", "budget_approval", "overhead", "procurement"].includes(k)).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select><button type="button" className="btn-ghost" onClick={() => set("reports", s.reports.filter((_, k) => k !== i))} aria-label="Remove this requirement">✕</button></div>
          <div className="onb-line"><select value={r.recurrence} onChange={(e) => setRep(i, { recurrence: e.target.value })} aria-label="How often">{Object.entries(REC).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select>
            {r.recurrence === "once" && <select value={r.anchor} onChange={(e) => setRep(i, { anchor: e.target.value })} aria-label="Due relative to">{["end", "start", "fixed"].map((k) => <option key={k} value={k}>{ANCHOR[k]}</option>)}</select>}
            {r.anchor === "fixed" && r.recurrence === "once" ? <input type="date" value={r.fixed_date} onChange={(e) => setRep(i, { fixed_date: e.target.value })} aria-label="Due date" /> : <label className="small muted">due <input type="number" min={0} style={{ width: 70 }} value={r.offset_days} onChange={(e) => setRep(i, { offset_days: Number(e.target.value) })} /> days {r.recurrence === "once" ? ANCHOR[r.anchor].replace("on a fixed date", "") : "after each period ends"}</label>}</div>
          <div className="onb-line"><input placeholder="Clause" style={{ maxWidth: 90 }} value={r.clause} onChange={(e) => setRep(i, { clause: e.target.value })} /><input placeholder="Language, e.g. en or fr" style={{ maxWidth: 150 }} value={r.language} onChange={(e) => setRep(i, { language: e.target.value })} /><input placeholder="Format or template" value={r.format} onChange={(e) => setRep(i, { format: e.target.value })} /><select value={r.detail} onChange={(e) => setRep(i, { detail: e.target.value })} aria-label="Level of detail">{o?.detail.map((d) => <option key={d} value={d}>{d}</option>)}</select></div>
        </div>)}
        <button type="button" className="btn-ghost" onClick={() => set("reports", [...s.reports, { canon: "narrative_report", title: "", recurrence: "once", anchor: "end", offset_days: 0, fixed_date: "", language: "", format: "", detail: "standard", clause: "", note: "" }])}>+ Add a custom requirement</button>
      </section>}

      {step === 3 && <section className="onb-card">
        <h3 className="serif">Other terms</h3>
        <F label="Visibility and acknowledgement" hint="How the funder must be credited">{area("visibility")}</F>
        <div className="onb-grid"><F label="Notice period to end the contract (days)"><input inputMode="numeric" value={s.notice} onChange={(e) => set("notice", e.target.value)} /></F><F label="Governing law and courts">{text("law")}</F></div>
        <F label="Ownership of results">{area("ownership")}</F>
        <F label="Data protection">{area("data")}</F>
        <F label="Special conditions">{area("special")}</F>
        <h3 className="serif">Contacts at the funder</h3>
        {s.contacts.map((c, i) => <div key={i} className="onb-line"><input placeholder="Name" value={c.name} onChange={(e) => setCon(i, { name: e.target.value })} /><input placeholder="Role" value={c.role} onChange={(e) => setCon(i, { role: e.target.value })} /><input placeholder="Email" value={c.email} onChange={(e) => setCon(i, { email: e.target.value })} /><input placeholder="Phone" value={c.phone} onChange={(e) => setCon(i, { phone: e.target.value })} /><button type="button" className="btn-ghost" onClick={() => set("contacts", s.contacts.filter((_, k) => k !== i))} aria-label="Remove this contact">✕</button></div>)}
        <button type="button" className="btn-ghost" onClick={() => set("contacts", [...s.contacts, { name: "", role: "", email: "", phone: "" }])}>+ Add a contact</button>
      </section>}

      {step === 4 && pv && <section className="onb-card">
        <h3 className="serif">Review</h3>
        {pv.errors.length > 0 && <div className="notice onb-err"><div><b>Please fix before saving:</b><ul>{pv.errors.map((e) => <li key={e}>{e}</li>)}</ul></div></div>}
        {pv.warnings.length > 0 && <div className="notice"><div><b>Worth a look:</b><ul>{pv.warnings.map((e) => <li key={e}>{e}</li>)}</ul></div></div>}
        <p>Saving will create {pv.summary.requirements} reporting requirement{pv.summary.requirements === 1 ? "" : "s"} with <b>{pv.summary.deadlines} deadline{pv.summary.deadlines === 1 ? "" : "s"}</b> (they will appear on the Today lake), {pv.summary.rules} contract rule{pv.summary.rules === 1 ? "" : "s"}{pv.summary.payments ? ` and ${pv.summary.payments} expected payment${pv.summary.payments === 1 ? "" : "s"}` : ""} for {pv.summary.funder || "the funder"}.</p>
        {pv.deadlines.length > 0 && <div className="onb-list">{pv.deadlines.map((d, i) => <div key={i} className="related-row"><span>{d.title}{d.period ? <span className="muted small"> · {d.period}</span> : null}</span><span className="muted small">{dateY(d.due_date)}</span></div>)}{pv.more_deadlines > 0 && <div className="muted small">…and {pv.more_deadlines} more</div>}</div>}
        {pv.rules.length > 0 && <div className="onb-list"><div className="kicker">RULES</div>{pv.rules.map((r) => <div key={r} className="related-row"><span>{r}</span></div>)}</div>}
        {pv.payments.length > 0 && <div className="onb-list"><div className="kicker">EXPECTED PAYMENTS</div>{pv.payments.map((p, i) => <div key={i} className="related-row"><span>{p.label}{p.condition ? <span className="muted small"> · {p.condition}</span> : null}</span><span className="muted small">{dateY(p.date)} · {money(p.amount == null ? null : Number(p.amount), s.cur)}</span></div>)}</div>}
      </section>}

      {err && <div className="edit-err">{err}</div>}
      <div className="onb-nav">
        {step > 0 && <button type="button" className="btn-ghost" onClick={() => setStep(step - 1)}>Back</button>}
        {step < 4 && <button type="button" className="btn-primary" disabled={busy} onClick={() => go(step + 1)}>{step === 3 ? "Review" : "Next"}</button>}
        {step === 4 && <button type="button" className="btn-primary" disabled={busy || !pv || pv.errors.length > 0} onClick={create}>Save the contract</button>}
        {funderCur && step === 1 && funderCur !== s.cur && <span className="small muted">Note: this funder's usual currency is {funderCur}.</span>}
      </div>
    </div>
  );
}
