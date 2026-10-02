import { useEffect, useState } from "react";
import { type AuditCompare, type AuditLine, type AuditStatus, getAuditCompare, getAuditLines, getAuditStatus, runAudit } from "../api";
import { dayFull, dayShort } from "../format";
import { Shell } from "../today/Drawer";

const money = (n: number) => n.toLocaleString("en-GB", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const LABEL: Record<string, string> = { "À JUSTIFIER": "Still to justify", "justifié": "Justified by a document", "couvert": "Covered (salary, bank fees, internal transfers…)" };

export default function AuditDrawer({ initial, onClose, onChanged }: { initial: AuditStatus | null; onClose: () => void; onChanged: () => void }) {
  const [st, setSt] = useState<AuditStatus | null>(initial);
  const [lines, setLines] = useState<AuditLine[] | null>(null);
  const [cmp, setCmp] = useState<AuditCompare | null>(null);
  const [showCmp, setShowCmp] = useState(false);
  const [err, setErr] = useState("");

  const refresh = () => getAuditStatus().then((s) => { setSt(s); if (s.latest) getAuditLines("À JUSTIFIER").then((r) => setLines(r.items)); });
  useEffect(() => { refresh(); }, []);                                                      // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { if (!st?.running) return; const t = setInterval(async () => { const s = await getAuditStatus(); setSt(s); if (!s.running) { refresh(); onChanged(); } }, 2500); return () => clearInterval(t); }, [st?.running]);   // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { if (showCmp && !cmp) getAuditCompare().then(setCmp).catch(() => setErr("Could not compare")); }, [showCmp, cmp]);

  const l = st?.latest;
  const recheck = async () => { setErr(""); try { await runAudit(); setSt((p) => p && { ...p, running: true }); setCmp(null); } catch (e) { setErr((e as Error).message); } };

  return (
    <Shell kicker="AUDIT READINESS" title={l ? `${Math.round(l.pct_ok ?? 0)}% of payments have their document` : "Audit readiness"} meta={l ? `Checked ${dayShort(l.finished_at.slice(0, 10))} ${l.finished_at.slice(11, 16)} · ${st?.year}` : ""} onClose={onClose}>
      {st && !st.configured && <p className="muted">The audit folder is not connected yet.</p>}
      {st?.last_error && <div className="edit-err">The last check failed: {st.last_error}</div>}
      {st?.stale && !st.running && <div className="notice"><span>Documents in your {st.year} folder have changed since this check.</span><button type="button" onClick={recheck}>Check again</button></div>}
      {st?.running && <div className="notice"><span>Reading your statements and receipts… this takes a few seconds.</span></div>}

      {l && (
        <>
          <div className="facts">
            <span>Statements read</span><span>{l.n_statements ?? "–"} ({l.accounts.length} account{l.accounts.length === 1 ? "" : "s"} with debits)</span>
            <span>Receipts indexed</span><span>{l.n_pieces ?? "–"}</span>
            <span>Debits checked</span><span>{l.debits}{l.period_from && l.period_to ? ` · ${dayShort(l.period_from)} to ${dayShort(l.period_to)}` : ""}</span>
            {l.statements_to && <><span>Statements run to</span><span>{dayFull(l.statements_to)}</span></>}
          </div>
          <div className="related">
            <div className="kicker">RESULT</div>
            {Object.entries(l.counts).map(([k, v]) => (
              <div key={k} className="rel-row"><span className={`chip ${k === "À JUSTIFIER" ? "chip-major" : k === "justifié" ? "chip-hard" : "chip-soft"}`}>{k}</span><span>{LABEL[k] ?? k}</span><small>{v.n} · {money(v.total)}</small></div>
            ))}
          </div>

          <div className="related">
            <div className="kicker">STILL TO JUSTIFY ({lines?.length ?? "…"})</div>
            {lines?.length === 0 && <div className="note">Nothing: every payment in this period has a document or is covered.</div>}
            {lines?.map((x, i) => (
              <div key={i} className="rel-row"><span className="mono rel-type">{x.date_raw}</span><span>{x.beneficiaire}</span><small>{x.devise} {money(x.montant)}</small></div>
            ))}
            <div className="note">File the missing document in your {st?.year} folder (naming: Fournisseur_Facture_n_CHFmontant_paye_JJ.MM.AAAA.pdf), then check again.</div>
          </div>
        </>
      )}

      <div className="editor-actions">
        <button type="button" className="btn-small" onClick={recheck} disabled={!st?.configured || st?.running}>{st?.running ? "Checking…" : "Check again now"}</button>
        <button type="button" className="link-quiet" onClick={() => setShowCmp((s) => !s)}>{showCmp ? "Hide" : "Compare with your own report file"}</button>
      </div>
      {err && <div className="edit-err">{err}</div>}

      {showCmp && cmp && (
        <div className="related">
          <div className="kicker">COMPARED WITH {cmp.report ?? "YOUR REPORT"}</div>
          {!cmp.report_found && <div className="note">There is no report file in the {st?.year} folder to compare with.</div>}
          {cmp.report_found && cmp.readable === false && <div className="note">The report file has no “Tous les débits” sheet.</div>}
          {cmp.readable && (
            <>
              <div className={cmp.same ? "added" : "notice"}>{cmp.same ? `✓ Identical to your report (${cmp.report_modified?.slice(0, 10)}), line by line.` : `Your report (${cmp.report_modified?.slice(0, 10)}) and this check differ on ${Math.max(cmp.only_in_report?.length ?? 0, cmp.only_in_run?.length ?? 0)} line(s). Usually that is because documents were filed since your report was made.`}</div>
              {!cmp.same && <div className="note">Your report: {Object.entries(cmp.report_counts ?? {}).map(([k, v]) => `${k} ${v}`).join(" · ")}<br />This check: {Object.entries(cmp.run_counts ?? {}).map(([k, v]) => `${k} ${v}`).join(" · ")}</div>}
              {(cmp.only_in_report ?? []).map((x, i) => <div key={"r" + i} className="rel-row"><span className="mono rel-type">YOUR REPORT</span><span>{x.date} · {x.beneficiaire}</span><small>{money(x.montant)} · {x.statut}</small></div>)}
              {(cmp.only_in_run ?? []).map((x, i) => <div key={"n" + i} className="rel-row"><span className="mono rel-type">NOW</span><span>{x.date} · {x.beneficiaire}</span><small>{money(x.montant)} · {x.statut}</small></div>)}
            </>
          )}
        </div>
      )}
      <div className="note">Your script runs unchanged inside the harness. Nothing is written to your folders, and statements and amounts stay on this Mac.</div>
    </Shell>
  );
}
