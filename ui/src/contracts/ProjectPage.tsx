import { Fragment, useCallback, useEffect, useMemo, useState } from "react";
import { type PMCrosswalk, type PMDetail, type PMFunder, type PMTranslation, type PMTransfer, confirmPMObligation, getPMFunders, getPMProject, receivePMTransfer, setPMDeadlineStatus, translatePM } from "../api";
import { dayShort } from "../format";
import { ContractForm, ExtendForm, FunderForm, ObligationForm, TransferForm } from "./Forms";
import { KIND, STATUS_LABEL, dateY, money, monthKey, monthName, rate, signedChf } from "./fmt";

function Strip({ d }: { d: PMDetail }) {
  const t = d.finance.totals;
  const pct = t.committed_chf_budget ? Math.round((100 * t.chf_received) / t.committed_chf_budget) : 0;
  const open = d.deadlines.filter((x) => x.status === "todo" || x.status === "drafting");
  return (
    <div className="pm-strip">
      <div><span className="pm-k">Budget (at contract rates)</span><b className="serif">{money(t.committed_chf_budget)}</b></div>
      <div><span className="pm-k">Received so far</span><b className="serif">{money(t.chf_received)}</b><span className="small muted">{pct}% of the budget</span></div>
      <div><span className="pm-k">Exchange effect so far</span><b className={`serif ${t.fx_difference < 0 ? "bad" : "good"}`}>{signedChf(t.fx_difference)}</b><span className="small muted">bank rate vs budget rate</span></div>
      <div><span className="pm-k">Late transfers</span><b className={`serif ${t.late_transfers ? "bad" : ""}`}>{t.late_transfers}</b></div>
      <div><span className="pm-k">Reports still to do</span><b className="serif">{open.length}</b><span className="small muted">{open[0] ? `next ${dayShort(open[0].due_date)}` : ""}</span></div>
    </div>
  );
}

function Alerts({ d }: { d: PMDetail }) {
  const late = d.finance.transfers.filter((t) => t.status === "late");
  if (!d.crunches.length && !late.length) return null;
  return (
    <div className="pm-alerts">
      {d.crunches.map((k) => <div key={k.from} className="notice warn-box"><span><b>{k.count} reports fall due between {dateY(k.from)} and {dateY(k.to)}:</b> {k.items.join(" · ")}</span></div>)}
      {late.map((t) => <div key={t.id} className="notice warn-box"><span><b>{t.funder} {t.label} is {t.days_late} days late</b> ({money(t.expected_amount, t.currency)} expected {dateY(t.expected_date)}){t.note ? `: ${t.note}` : ""}</span></div>)}
    </div>
  );
}

function Contracts({ d, onChanged }: { d: PMDetail; onChanged: () => void }) {
  const [ext, setExt] = useState<number | null>(null);
  const top = d.contracts.filter((c) => c.kind !== "amendment");
  return (
    <section className="pm-section"><h3 className="serif">Funders and contracts</h3>
      <div className="tablewrap"><table className="pm-table">
        <thead><tr><th>Funder</th><th>Contract</th><th>Period</th><th className="r">Amount</th><th className="r">Budget rate</th><th>Signed copy</th><th /></tr></thead>
        <tbody>{top.map((c) => (<Fragment key={c.id}>
          <tr><td><b>{c.funder}</b><div className="small muted">{c.funder_name}</div></td>
            <td>{c.title}<div className="small muted">{KIND[c.kind]}{c.status === "amended" ? " · amended" : ""}</div>{c.summary && <div className="small muted">{c.summary}</div>}</td>
            <td className="nowrap">{dateY(c.start_date)} → {dateY(c.end_date)}</td>
            <td className="r nowrap">{money(c.amount, c.currency)}</td><td className="r">{c.currency === "CHF" ? "–" : rate(c.budget_rate)}</td>
            <td className="small">{c.file_path ? <><span className="mono">{c.file_path}</span><div className="muted">fingerprint {c.file_hash}</div></> : <span className="muted">not recorded</span>}</td>
            <td>{c.kind === "grant" && <button type="button" className="btn-ghost" onClick={() => setExt(ext === c.id ? null : c.id)}>Extension</button>}</td></tr>
          {d.contracts.filter((a) => a.parent_id === c.id).map((a) => (
            <tr key={a.id} className="pm-amend"><td /><td>↳ {a.title}<div className="small muted">Signed {dateY(a.signed_date)} · {a.summary}</div></td><td className="nowrap">→ {dateY(a.end_date)}</td><td colSpan={2} className="small muted">no change in amount</td>
              <td className="small">{a.file_path && <span className="mono">{a.file_path}</span>}</td><td /></tr>))}
          {ext === c.id && <tr key={`e${c.id}`}><td colSpan={7}><ExtendForm c={c} onDone={() => { setExt(null); onChanged(); }} /></td></tr>}
        </Fragment>))}</tbody></table></div>
      <div className="small muted">Contracts stay in your folders; the harness keeps only where they are and a fingerprint. Passed on to partners (budget rate): {money(d.finance.totals.passed_to_partners_chf_budget)}.</div>
    </section>
  );
}

function Calendar({ d, onChanged }: { d: PMDetail; onChanged: () => void }) {
  const [onlyOpen, setOnlyOpen] = useState(true);
  const rows = d.deadlines.filter((x) => !onlyOpen || x.status === "todo" || x.status === "drafting");
  const groups = useMemo(() => { const m = new Map<string, typeof rows>(); rows.forEach((r) => m.set(monthKey(r.due_date), [...(m.get(monthKey(r.due_date)) ?? []), r])); return [...m.entries()]; }, [rows]);
  const shown = groups.slice(0, onlyOpen ? 6 : 100);
  return (
    <section className="pm-section"><div className="pm-head"><h3 className="serif">Reporting calendar</h3>
      <label className="small muted"><input type="checkbox" checked={onlyOpen} onChange={(e) => setOnlyOpen(e.target.checked)} /> Only what is still open</label></div>
      {shown.length === 0 && <p className="muted">Nothing open.</p>}
      {shown.map(([k, items]) => (
        <div key={k} className="pm-month"><div className="kicker">{monthName(k).toUpperCase()}</div>
          {items.map((r) => (
            <div key={r.id} className={`pm-dl ${r.overdue ? "overdue" : ""}`}>
              <span className="pm-date mono">{dayShort(r.due_date)}</span><span className={`pm-chip pm-${r.role}`}>{r.funder}</span>
              <span className="pm-dl-title">{r.title}{!["fixed date", "final", "start"].includes(r.period) && <span className="muted small"> ({r.period})</span>}</span>
              <span className="small muted pm-left">{r.status === "todo" || r.status === "drafting" ? (r.days_left < 0 ? `${-r.days_left} d overdue` : r.days_left === 0 ? "today" : `in ${r.days_left} d`) : r.submitted_on ? `done ${dayShort(r.submitted_on)}` : ""}</span>
              <select value={r.status} onChange={async (e) => { await setPMDeadlineStatus(r.id, e.target.value); onChanged(); }} aria-label={`Status of ${r.title}`} className={`pm-status s-${r.status}`}>
                {Object.entries(STATUS_LABEL).map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select>
            </div>))}
        </div>))}
      {onlyOpen && groups.length > 6 && <div className="small muted">Showing the next six months with something due; untick the box for everything.</div>}
    </section>
  );
}

function Receive({ t, onDone }: { t: PMTransfer; onDone: () => void }) {
  const [date, setDate] = useState(new Date().toISOString().slice(0, 10)); const [amt, setAmt] = useState(String(t.expected_amount ?? "")); const [chf, setChf] = useState(""); const [rt, setRt] = useState(""); const [err, setErr] = useState("");
  const num = (v: string) => (v.trim() === "" ? undefined : Number(v));
  return (
    <form className="pm-form" onSubmit={async (e) => { e.preventDefault(); setErr(""); try { await receivePMTransfer(t.id, { received_date: date, received_amount: num(amt), chf_received: num(chf), bank_rate: num(rt) }); onDone(); } catch (x) { setErr((x as Error).message); } }}>
      <div className="pm-form-row"><label className="small muted">Arrived <input type="date" value={date} onChange={(e) => setDate(e.target.value)} required /></label>
        <input value={amt} onChange={(e) => setAmt(e.target.value)} inputMode="decimal" placeholder={`Received (${t.currency})`} aria-label="Received amount" />
        {t.currency !== "CHF" && <><input value={chf} onChange={(e) => setChf(e.target.value)} inputMode="decimal" placeholder="CHF credited" aria-label="CHF credited" /><input value={rt} onChange={(e) => setRt(e.target.value)} inputMode="decimal" placeholder="Bank rate" aria-label="Bank rate" /></>}
        <button type="submit" className="btn-primary">Record receipt</button></div>
      {t.currency !== "CHF" && <div className="small muted">Enter the CHF the bank credited, or the bank's rate: the other is worked out. The rate that counts is the one the bank assigned when it arrived.</div>}
      {err && <div className="edit-err">{err}</div>}
    </form>
  );
}

function Transfers({ d, onChanged }: { d: PMDetail; onChanged: () => void }) {
  const [open, setOpen] = useState<number | null>(null);
  return (
    <section className="pm-section"><h3 className="serif">Funding transfers</h3>
      <div className="tablewrap"><table className="pm-table">
        <thead><tr><th>Funder</th><th>Transfer</th><th>Expected</th><th>Arrived</th><th className="r">Bank rate</th><th className="r">CHF credited</th><th className="r">vs budget rate</th><th /></tr></thead>
        <tbody>{d.finance.transfers.map((t) => (<Fragment key={t.id}>
          <tr className={t.status === "late" ? "pm-late" : ""}>
            <td><b>{t.funder}</b></td><td>{t.label}{t.note && <div className="small muted">{t.note}</div>}</td>
            <td className="nowrap">{dateY(t.expected_date)}<div className="small muted">{money(t.expected_amount, t.currency)}</div></td>
            <td className="nowrap">{t.received_date ? <>{dateY(t.received_date)}<div className="small muted">{money(t.received_amount, t.currency)}{t.days_late ? ` · ${t.days_late} d late` : ""}</div></> : <span className={t.status === "late" ? "bad" : "muted"}>{t.status === "late" ? `late by ${t.days_late} d` : "not yet"}</span>}</td>
            <td className="r">{t.currency === "CHF" ? "–" : rate(t.bank_rate)}{t.currency !== "CHF" && t.received_date && <div className="small muted">budget {rate(t.budget_rate)}</div>}</td>
            <td className="r">{t.chf_received != null ? money(t.chf_received) : "–"}</td>
            <td className={`r ${t.fx_difference != null && t.fx_difference < 0 ? "bad" : "good"}`}>{t.fx_difference != null ? signedChf(t.fx_difference) : ""}</td>
            <td>{!t.received_date && <button type="button" className="btn-ghost" onClick={() => setOpen(open === t.id ? null : t.id)}>Arrived</button>}</td></tr>
          {open === t.id && <tr key={`r${t.id}`}><td colSpan={8}><Receive t={t} onDone={() => { setOpen(null); onChanged(); }} /></td></tr>}
        </Fragment>))}</tbody></table></div>
      <div className="pm-perc">{d.finance.contracts.filter((c) => c.kind === "grant").map((c) => (
        <div key={c.contract_id}><b>{c.funder}</b> <span className="muted small">{money(c.received, c.currency)} of {money(c.amount, c.currency)}{c.currency !== "CHF" && c.average_rate ? ` · average rate ${rate(c.average_rate)}` : ""}</span>
          <div className="pm-bar"><i style={{ width: `${c.amount ? Math.min(100, (100 * c.received) / c.amount) : 0}%` }} /></div></div>))}</div>
    </section>
  );
}

function Crosswalk({ d, onChanged }: { d: PMDetail; onChanged: () => void }) {
  const funders = d.funders;
  const [from, setFrom] = useState(funders[1] ?? funders[0] ?? ""); const [to, setTo] = useState(funders[0] ?? "");
  const [tr, setTr] = useState<PMTranslation | null>(null); const [err, setErr] = useState("");
  const go = async () => { setErr(""); try { setTr(await translatePM(d.project.id, from, to)); } catch (e) { setErr((e as Error).message); } };
  const multi = d.crosswalk.filter((g) => g.funders.length > 1);
  return (
    <section className="pm-section"><h3 className="serif">What each funder asks for</h3>
      <p className="muted small">Each funder's clauses are mapped to common requirement types, so you can see what one piece of work can cover for several funders. Mappings marked “proposed” are waiting for your confirmation.</p>
      <div className="pm-translate"><b>Translate:</b> what I already do for
        <select value={from} onChange={(e) => setFrom(e.target.value)} aria-label="From funder">{funders.map((f) => <option key={f}>{f}</option>)}</select> covers for
        <select value={to} onChange={(e) => setTo(e.target.value)} aria-label="To funder">{funders.map((f) => <option key={f}>{f}</option>)}</select>
        <button type="button" className="btn-primary" onClick={go} disabled={from === to}>Compare</button></div>
      {err && <div className="edit-err">{err}</div>}
      {tr && (
        <div className="pm-tr">
          <div className="small"><b>{tr.from} → {tr.to}:</b> {tr.summary.covers} covered · {tr.summary.partly} need adapting · {tr.summary.gap} still to produce</div>
          {tr.rows.map((r, i) => (
            <div key={i} className={`pm-tr-row v-${r.verdict}`}><span className="pm-verdict">{r.verdict === "covers" ? "Covered" : r.verdict === "partly" ? "Adapt" : "New work"}</span><b>{r.label}</b>
              <ul>{r.reasons.map((x, j) => <li key={j}>{x}</li>)}</ul></div>))}
        </div>)}
      {d.crosswalk.map((g: PMCrosswalk) => (
        <details key={g.canon} className="pm-cw" open={g.funders.length > 1 && multi.length <= 4}>
          <summary><b>{g.label}</b> <span className="muted small">{g.funders.join(", ")}</span>{g.unconfirmed > 0 && <span className="pm-prop">{g.unconfirmed} proposed</span>}</summary>
          <div className="tablewrap"><table className="pm-table">
            <thead><tr><th>Funder</th><th>Requirement</th><th>Timing</th><th>Language</th><th>Format</th><th>Detail</th><th /></tr></thead>
            <tbody>{g.items.map((o) => (
              <tr key={o.id}><td><b>{o.funder}</b></td><td>{o.title}{o.clause && <div className="small muted">{o.clause}</div>}</td><td className="small">{o.rule}</td><td>{o.language ?? "–"}</td><td className="small">{o.format ?? "–"}</td><td>{o.detail ?? "–"}</td>
                <td>{!o.confirmed && <button type="button" className="btn-ghost" onClick={async () => { await confirmPMObligation(o.id); onChanged(); }}>Confirm</button>}</td></tr>))}</tbody></table></div>
          {g.funders.length > 1 && <div className="pm-plan"><div className="small muted">{g.same.length ? `The same: ${g.same.join(", ")}. ` : ""}{g.differs.length ? `Differs: ${g.differs.join(", ")}.` : ""}</div><div><b>Combined plan:</b> {g.plan}</div></div>}
        </details>))}
    </section>
  );
}

export default function ProjectPage({ id, onBack, onChanged }: { id: number; onBack: () => void; onChanged: () => void }) {
  const [d, setD] = useState<PMDetail | null>(null);
  const [funders, setFunders] = useState<PMFunder[]>([]);
  const [add, setAdd] = useState<"" | "funder" | "contract" | "obligation" | "transfer">("");
  const load = useCallback(() => { getPMProject(id).then(setD).catch(() => setD(null)); getPMFunders().then(setFunders).catch(() => {}); onChanged(); }, [id, onChanged]);
  useEffect(() => { load(); }, [load]);
  if (!d) return <p className="muted">Loading…</p>;
  const done = () => { setAdd(""); load(); };
  return (
    <div className="pm-project">
      <button type="button" className="btn-ghost pm-back" onClick={onBack}>← All projects</button>
      <header className="pm-title"><div><span className="mono proj-code">{d.project.code}</span> {d.project.demo && <span className="pm-prop">demo data</span>}<h2 className="serif">{d.project.name}</h2>
        <div className="muted small">{dateY(d.project.start_date)} → {dateY(d.project.end_date)}{d.project.lead ? ` · ${d.project.lead}` : ""}</div></div>
        <div className="pm-chips">{d.funders.map((f) => <span key={f} className="pm-chip pm-funder">{f}</span>)}</div></header>
      {d.project.summary && <p className="pm-summary">{d.project.summary}</p>}
      <Strip d={d} /><Alerts d={d} />
      <Contracts d={d} onChanged={load} /><Calendar d={d} onChanged={load} /><Transfers d={d} onChanged={load} /><Crosswalk d={d} onChanged={load} />
      <section className="pm-section"><h3 className="serif">Add to this project</h3>
        <div className="pm-adds">{([["funder", "A funder or partner"], ["contract", "A contract"], ["obligation", "A requirement"], ["transfer", "A funding transfer"]] as const).map(([k, l]) => (
          <button key={k} type="button" className={add === k ? "btn-primary" : "btn-ghost"} onClick={() => setAdd(add === k ? "" : k)}>{l}</button>))}</div>
        {add === "funder" && <FunderForm onDone={done} />}{add === "contract" && <ContractForm d={d} funders={funders} onDone={done} />}
        {add === "obligation" && <ObligationForm d={d} onDone={done} />}{add === "transfer" && <TransferForm d={d} onDone={done} />}
      </section>
    </div>
  );
}
