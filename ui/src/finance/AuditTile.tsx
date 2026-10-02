import { useCallback, useEffect, useState } from "react";
import { type AuditStatus, getAuditStatus } from "../api";
import { dayShort } from "../format";

/** The "Audit readiness" widget: how many payments have their document. Click for the detail. */
export function useAuditStatus() {
  const [st, setSt] = useState<AuditStatus | null>(null);
  const load = useCallback(() => getAuditStatus().then(setSt).catch(() => setSt(null)), []);
  useEffect(() => { load(); }, [load]);
  useEffect(() => { const t = setInterval(load, st?.running ? 3000 : 60_000); return () => clearInterval(t); }, [load, st?.running]);
  return { st, reload: load };
}

export default function AuditTile({ st, onOpen }: { st: AuditStatus | null; onOpen: () => void }) {
  const l = st?.latest;
  const pct = l?.pct_ok ?? null;
  const missing = l ? l.counts["À JUSTIFIER"]?.n ?? 0 : 0;
  let head = "—", sub = "Checking…", note = "Click for the detail";
  if (st && !st.configured) { sub = "Connect the audit folder"; }
  else if (st?.running) { head = "…"; sub = "Checking your statements"; }
  else if (l && pct !== null) {
    head = `${Math.round(pct)}%`;
    sub = missing === 0 ? `Every payment to ${l.period_to ? dayShort(l.period_to) : "date"} has its document`
      : `${missing} payment${missing === 1 ? "" : "s"} still need${missing === 1 ? "s" : ""} a document`;
    if (st?.stale) note = "New documents since the check · open to re-check";
  } else if (st) { sub = st.last_error ? "The check failed" : "Not checked yet"; }
  const ring = pct === null ? "conic-gradient(#e0e4f0 0 100%)" : `conic-gradient(${pct >= 100 ? "var(--lime)" : "var(--purple)"} ${pct}%, #e0e4f0 0)`;
  return (
    <button type="button" className="tile tile-live" onClick={onOpen} aria-label="Open audit readiness">
      <div className="tile-art ring-art"><div className="ring" style={{ background: ring }}><div className="ring-hole" /></div></div>
      <div className="tile-text">
        <span className="tile-title">Audit readiness</span>
        <span className="serif tile-head">{head}</span>
        <span className="tile-sub">{sub}</span>
        <span className={`soon ${st?.stale ? "warn" : ""}`}>{note}</span>
      </div>
    </button>
  );
}
