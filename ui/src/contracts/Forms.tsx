import { useState } from "react";
import { type PMContract, type PMDetail, type PMFunder, addPMContract, addPMFunder, addPMObligation, addPMTransfer, extendPMContract } from "../api";

function useForm(onDone: () => void) {
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const run = async (fn: () => Promise<unknown>) => { setErr(""); setBusy(true); try { await fn(); onDone(); } catch (e) { setErr((e as Error).message); } finally { setBusy(false); } };
  return { err, busy, run };
}
const num = (v: string) => (v.trim() === "" ? undefined : Number(v));
const Row = ({ children }: { children: React.ReactNode }) => <div className="pm-form-row">{children}</div>;

export function FunderForm({ onDone }: { onDone: () => void }) {
  const f = useForm(onDone);
  const [name, setName] = useState(""); const [short, setShort] = useState(""); const [cur, setCur] = useState("CHF"); const [role, setRole] = useState("funder");
  return (
    <form className="pm-form" onSubmit={(e) => { e.preventDefault(); f.run(() => addPMFunder({ name, short: short || undefined, currency: cur, role })); }}>
      <Row><input value={name} onChange={(e) => setName(e.target.value)} placeholder="Name of the funder or partner" aria-label="Name" required />
        <input value={short} onChange={(e) => setShort(e.target.value)} placeholder="Short name" maxLength={12} aria-label="Short name" />
        <input value={cur} onChange={(e) => setCur(e.target.value.toUpperCase())} maxLength={3} aria-label="Currency" style={{ width: 64 }} />
        <select value={role} onChange={(e) => setRole(e.target.value)} aria-label="Role"><option value="funder">Funder</option><option value="partner">Partner</option></select></Row>
      {f.err && <div className="edit-err">{f.err}</div>}
      <button type="submit" className="btn-primary" disabled={f.busy}>Add</button>
    </form>
  );
}

export function ContractForm({ d, funders, onDone }: { d: PMDetail; funders: PMFunder[]; onDone: () => void }) {
  const f = useForm(onDone);
  const [funder, setFunder] = useState(funders[0]?.id ?? 0); const [title, setTitle] = useState(""); const [kind, setKind] = useState("grant");
  const [amount, setAmount] = useState(""); const [rate, setRate] = useState(""); const [start, setStart] = useState(d.project.start_date ?? ""); const [end, setEnd] = useState(d.project.end_date ?? "");
  const [path, setPath] = useState(""); const [signed, setSigned] = useState("");
  const cur = funders.find((x) => x.id === Number(funder))?.currency ?? "CHF";
  return (
    <form className="pm-form" onSubmit={(e) => { e.preventDefault(); f.run(() => addPMContract({ project_id: d.project.id, funder_id: Number(funder), title, kind, amount: num(amount), budget_rate: num(rate), start_date: start || null, end_date: end || null, signed_date: signed || null, file_path: path || null })); }}>
      <Row><select value={funder} onChange={(e) => setFunder(Number(e.target.value))} aria-label="Funder or partner">{funders.map((x) => <option key={x.id} value={x.id}>{x.short} ({x.currency})</option>)}</select>
        <select value={kind} onChange={(e) => setKind(e.target.value)} aria-label="Kind"><option value="grant">Grant (money in)</option><option value="subgrant">Sub-grant (money out)</option></select>
        <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Title, e.g. Grant agreement" aria-label="Title" required /></Row>
      <Row><input value={amount} onChange={(e) => setAmount(e.target.value)} inputMode="decimal" placeholder={`Amount (${cur})`} aria-label="Amount" />
        {cur !== "CHF" && <input value={rate} onChange={(e) => setRate(e.target.value)} inputMode="decimal" placeholder={`Budget rate (CHF per 1 ${cur})`} aria-label="Budget rate" />}
        <label className="small muted">Signed <input type="date" value={signed} onChange={(e) => setSigned(e.target.value)} /></label>
        <label className="small muted">From <input type="date" value={start} onChange={(e) => setStart(e.target.value)} /></label>
        <label className="small muted">To <input type="date" value={end} onChange={(e) => setEnd(e.target.value)} /></label></Row>
      <Row><input value={path} onChange={(e) => setPath(e.target.value)} placeholder="Where the signed contract is kept (path in your folders)" aria-label="Contract location" /></Row>
      {f.err && <div className="edit-err">{f.err}</div>}
      <button type="submit" className="btn-primary" disabled={f.busy || !funders.length}>Add contract</button>
    </form>
  );
}

export function ExtendForm({ c, onDone, onCancel }: { c: PMContract; onDone: () => void; onCancel: () => void }) {
  const f = useForm(onDone);
  const [end, setEnd] = useState(""); const [title, setTitle] = useState("No-cost extension");
  return (
    <form className="pm-form" onSubmit={(e) => { e.preventDefault(); f.run(() => extendPMContract(c.id, { new_end: end, title })); }}>
      <Row><input value={title} onChange={(e) => setTitle(e.target.value)} aria-label="Title of the amendment" />
        <label className="small muted">New end date <input type="date" value={end} onChange={(e) => setEnd(e.target.value)} required /></label>
        <button type="submit" className="btn-primary" disabled={f.busy}>Record the extension</button>
        <button type="button" className="btn-ghost" onClick={onCancel}>Cancel</button></Row>
      <div className="small muted">Adds the amendment, moves the end date, and adds the new reporting periods and moves the final report.</div>
      {f.err && <div className="edit-err">{f.err}</div>}
    </form>
  );
}

export function ObligationForm({ d, onDone }: { d: PMDetail; onDone: () => void }) {
  const f = useForm(onDone);
  const own = d.contracts.filter((c) => c.kind !== "amendment");
  const [contract, setContract] = useState(own[0]?.id ?? 0); const [canon, setCanon] = useState("narrative_report"); const [title, setTitle] = useState("");
  const [recurrence, setRecurrence] = useState("annual"); const [offset, setOffset] = useState("30"); const [anchor, setAnchor] = useState("period_end"); const [fixed, setFixed] = useState("");
  const [lang, setLang] = useState(""); const [format, setFormat] = useState(""); const [detail, setDetail] = useState(""); const [clause, setClause] = useState("");
  const rule = recurrence === "none";
  return (
    <form className="pm-form" onSubmit={(e) => { e.preventDefault(); f.run(() => addPMObligation({ contract_id: Number(contract), canon, title, clause: clause || null, anchor: rule ? "none" : recurrence === "once" ? anchor : "period_end", offset_days: Number(offset) || 0, recurrence, fixed_date: anchor === "fixed" && recurrence === "once" ? fixed : null, language: lang || null, format: format || null, detail: detail || null })); }}>
      <Row><select value={contract} onChange={(e) => setContract(Number(e.target.value))} aria-label="Contract">{own.map((c) => <option key={c.id} value={c.id}>{c.funder}: {c.title}</option>)}</select>
        <select value={canon} onChange={(e) => setCanon(e.target.value)} aria-label="Requirement type">{Object.entries(d.canon).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select>
        <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="What exactly is required" aria-label="Title" required /></Row>
      <Row><select value={recurrence} onChange={(e) => setRecurrence(e.target.value)} aria-label="How often">
          <option value="none">An ongoing rule (no deadline)</option><option value="once">Once</option><option value="quarterly">Every quarter</option><option value="semiannual">Every six months</option><option value="annual">Every year</option></select>
        {recurrence === "once" && <select value={anchor} onChange={(e) => setAnchor(e.target.value)} aria-label="Counted from"><option value="end">After the contract end</option><option value="start">After the contract start</option><option value="fixed">On a fixed date</option></select>}
        {recurrence === "once" && anchor === "fixed" ? <input type="date" value={fixed} onChange={(e) => setFixed(e.target.value)} aria-label="Fixed date" required />
          : !rule && <label className="small muted">Days after the {recurrence === "once" ? (anchor === "start" ? "start" : "end") : "end of each period"} <input value={offset} onChange={(e) => setOffset(e.target.value)} inputMode="numeric" style={{ width: 56 }} /></label>}</Row>
      <Row><input value={lang} onChange={(e) => setLang(e.target.value)} placeholder="Language(s), e.g. fr,en" aria-label="Language" />
        <input value={format} onChange={(e) => setFormat(e.target.value)} placeholder="Format or template" aria-label="Format" />
        <select value={detail} onChange={(e) => setDetail(e.target.value)} aria-label="Level of detail"><option value="">Level of detail</option><option value="summary">Summary</option><option value="standard">Standard</option><option value="detailed">Detailed</option><option value="line-by-line">Line by line</option></select>
        <input value={clause} onChange={(e) => setClause(e.target.value)} placeholder="Clause, e.g. Art. 7.1" aria-label="Clause" style={{ width: 130 }} /></Row>
      {f.err && <div className="edit-err">{f.err}</div>}
      <button type="submit" className="btn-primary" disabled={f.busy || !own.length}>Add requirement</button>
    </form>
  );
}

export function TransferForm({ d, onDone }: { d: PMDetail; onDone: () => void }) {
  const f = useForm(onDone);
  const own = d.contracts.filter((c) => c.kind === "grant");
  const [contract, setContract] = useState(own[0]?.id ?? 0); const [label, setLabel] = useState(""); const [expDate, setExpDate] = useState(""); const [expAmt, setExpAmt] = useState("");
  const [recDate, setRecDate] = useState(""); const [recAmt, setRecAmt] = useState(""); const [chf, setChf] = useState(""); const [rate, setRate] = useState(""); const [ref, setRef] = useState("");
  const cur = own.find((c) => c.id === Number(contract))?.currency ?? "CHF";
  return (
    <form className="pm-form" onSubmit={(e) => { e.preventDefault(); f.run(() => addPMTransfer({ contract_id: Number(contract), label, expected_date: expDate || null, expected_amount: num(expAmt), received_date: recDate || null, received_amount: num(recAmt), chf_received: num(chf), bank_rate: num(rate), bank_ref: ref || null })); }}>
      <Row><select value={contract} onChange={(e) => setContract(Number(e.target.value))} aria-label="Grant">{own.map((c) => <option key={c.id} value={c.id}>{c.funder} ({c.currency})</option>)}</select>
        <input value={label} onChange={(e) => setLabel(e.target.value)} placeholder="Label, e.g. Instalment 3" aria-label="Label" required />
        <label className="small muted">Expected <input type="date" value={expDate} onChange={(e) => setExpDate(e.target.value)} /></label>
        <input value={expAmt} onChange={(e) => setExpAmt(e.target.value)} inputMode="decimal" placeholder={`Expected (${cur})`} aria-label="Expected amount" /></Row>
      <div className="small muted">If it has arrived, fill in what the bank shows. For {cur === "CHF" ? "a CHF transfer just the amount" : `a ${cur} transfer two of the three: amount, CHF credited, the bank's rate`}.</div>
      <Row><label className="small muted">Arrived <input type="date" value={recDate} onChange={(e) => setRecDate(e.target.value)} /></label>
        <input value={recAmt} onChange={(e) => setRecAmt(e.target.value)} inputMode="decimal" placeholder={`Received (${cur})`} aria-label="Received amount" />
        {cur !== "CHF" && <><input value={chf} onChange={(e) => setChf(e.target.value)} inputMode="decimal" placeholder="CHF credited" aria-label="CHF credited" />
          <input value={rate} onChange={(e) => setRate(e.target.value)} inputMode="decimal" placeholder="Bank rate (CHF per 1)" aria-label="Bank rate" /></>}
        <input value={ref} onChange={(e) => setRef(e.target.value)} placeholder="Bank reference" aria-label="Bank reference" /></Row>
      {f.err && <div className="edit-err">{f.err}</div>}
      <button type="submit" className="btn-primary" disabled={f.busy || !own.length}>Add transfer</button>
    </form>
  );
}
