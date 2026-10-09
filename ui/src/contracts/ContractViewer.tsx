import { type PMContract, type PMObligation } from "../api";
import { Shell } from "../today/Drawer";
import { KIND, dateY, money, rate } from "./fmt";

/** The underlying contract, in a pop-out on the side: the PDF itself (when the harness holds it) with a download button, and what the contract requires. Real contracts stay in your folders; for those only the location is shown. */
export default function ContractViewer({ c, obligations, onClose }: { c: PMContract; obligations: PMObligation[]; onClose: () => void }) {
  const mine = obligations.filter((o) => o.contract_id === c.id || (c.parent_id != null && o.contract_id === c.parent_id));
  const name = c.file_path?.split("/").pop() ?? "";
  return (
    <Shell kicker={`CONTRACT · ${c.funder}`} title={c.title} meta={`${KIND[c.kind]} · ${money(c.amount, c.currency)} · ${dateY(c.start_date)} → ${dateY(c.end_date)}`} onClose={onClose} wide>
      <div className="facts"><span>Funder</span><span>{c.funder_name}</span><span>Signed</span><span>{dateY(c.signed_date)}</span><span>Amount</span><span>{money(c.amount, c.currency)}</span>
        {c.currency !== "CHF" && <><span>Budget rate</span><span>{rate(c.budget_rate)} CHF per 1 {c.currency}</span></>}
        <span>Kept at</span><span className="mono small">{c.file_path ?? "not recorded"}</span>{c.file_hash && <><span>Fingerprint</span><span className="mono small">{c.file_hash}…</span></>}</div>
      {c.has_file ? (
        <>
          <div className="chat-prop-row">
            <a className="btn-primary link-btn" href={`/api/pm/contracts/${c.id}/pdf?download=1`}>Download the PDF</a>
            <a className="btn-ghost link-btn" href={`/api/pm/contracts/${c.id}/pdf`} target="_blank" rel="noopener noreferrer">Open in a new tab</a>
          </div>
          <iframe className="pdf-frame" title={`Contract: ${c.title}`} src={`/api/pm/contracts/${c.id}/pdf#navpanes=0&view=FitH`} />
        </>
      ) : (
        <div className="notice"><span>This contract stays in your folders: the harness only knows where it is kept{name ? ` (${name})` : ""}. Open it from there.</span>
          {c.file_path && <button type="button" className="btn-ghost" onClick={() => navigator.clipboard?.writeText(c.file_path ?? "").catch(() => {})}>Copy path</button>}</div>
      )}
      <div className="related"><div className="kicker">WHAT THIS CONTRACT REQUIRES ({mine.length})</div>
        {mine.length === 0 ? <p className="muted">No requirements recorded yet.</p> : mine.map((o) => (
          <div key={o.id} className="related-row"><span>{o.title}{o.clause ? <span className="muted small"> · {o.clause}</span> : null}</span><span className="muted small">{o.rule}</span></div>))}</div>
    </Shell>
  );
}
