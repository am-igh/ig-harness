import { type ScanSummary } from "../api";

/** The "Scan inbox" widget: what is waiting for her decision. */
export default function ScanTile({ s, onOpen }: { s: ScanSummary | null; onOpen: () => void }) {
  const head = !s ? "—" : s.to_confirm > 0 ? `${s.to_confirm} to confirm` : s.reading > 0 ? "Reading…" : "All clear";
  const sub = !s ? "Checking…" : s.failed > 0 ? `${s.failed} could not be filed` : `${s.filed_this_week} filed this week`;
  return (
    <button type="button" className="tile tile-live" onClick={onOpen} aria-label="Open the scan inbox">
      <div className="tile-art cal-art"><span className="serif cal-art-day">{s?.to_confirm ?? "·"}</span></div>
      <div className="tile-text"><span className="tile-title">Scan inbox</span><span className="serif tile-head">{head}</span><span className="tile-sub">{sub}</span><span className="soon">Review and file →</span></div>
    </button>
  );
}
