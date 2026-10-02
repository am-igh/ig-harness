import { useCallback, useEffect, useRef, useState } from "react";
import { type Filing, approveFiling, getFilings, skipFiling, uploadStatement } from "../api";
import { dayShort } from "../format";

const BAD = new Set(["duplicate", "name_taken", "same_period", "wrong_year", "not_statement", "unreadable"]);

/** Add the quarterly UBS statements: choose the PDFs, read each preview, approve. The harness adds each as a NEW file in the audit folder, never overwriting. */
export default function StatementsBox({ onFiled }: { onFiled: () => void }) {
  const [items, setItems] = useState<Filing[]>([]);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  const load = useCallback(() => getFilings().then((r) => setItems(r.items)).catch(() => undefined), []);
  useEffect(() => { load(); }, [load]);
  const waiting = items.some((i) => i.status === "approved");
  useEffect(() => { if (!waiting) return; const t = setInterval(async () => { await load(); }, 3000); return () => clearInterval(t); }, [waiting, load]);
  const wasWaiting = useRef(false);
  useEffect(() => { if (wasWaiting.current && !waiting) onFiled(); wasWaiting.current = waiting; }, [waiting, onFiled]);

  const pick = async (files: FileList | null) => {
    if (!files?.length) return;
    setBusy(true); setErr("");
    for (const f of Array.from(files)) { try { await uploadStatement(f); } catch (e) { setErr(`${f.name}: ${(e as Error).message}`); } }
    setBusy(false); if (input.current) input.current.value = ""; load();
  };
  const act = async (fn: () => Promise<unknown>) => { setErr(""); try { await fn(); } catch (e) { setErr((e as Error).message); } load(); };
  const visible = items.filter((i) => i.status !== "skipped").slice(0, 12);
  const ready = visible.filter((i) => i.state === "new" && i.status === "staged");

  return (
    <section className="card-box stmt-box" aria-label="Bank statements">
      <div className="stmt-head"><h3>Bank statements</h3>
        <button type="button" className="btn-small" disabled={busy} onClick={() => input.current?.click()}>{busy ? "Reading…" : "Add bank statements"}</button>
        <input ref={input} type="file" accept="application/pdf,.pdf" multiple hidden onChange={(e) => pick(e.target.files)} />
      </div>
      <div className="note">Choose the UBS statement PDFs you downloaded. Each is read on this Mac, shown here, and added to your audit folder as a new file only after you approve it. Nothing is ever overwritten.</div>
      {err && <div className="edit-err">{err}</div>}
      {visible.map((f) => (
        <div key={f.id} className={`stmt-row ${BAD.has(f.state) ? "stmt-bad" : ""}`}>
          <div className="stmt-main">
            <span className="mono stmt-name">{f.original_name}</span>
            <span className="stmt-detail">
              {f.period_from && f.period_to ? `${f.account_label ?? ""} · ${dayShort(f.period_from)} to ${dayShort(f.period_to)}${f.period_kind ? ` (${f.period_kind.toLowerCase()})` : ""} · ` : ""}{f.detail}
            </span>
            {f.status === "approved" && <span className="soon">Filing…</span>}
            {f.status === "filed" && <span className="stmt-ok">✓ Added to the {f.year} folder. Re-checking the audit.</span>}
            {f.status === "failed" && <span className="warn-text">Not filed: {f.result}</span>}
          </div>
          {f.state === "new" && f.status === "staged" && (
            <div className="stmt-actions">
              <button type="button" className="btn-primary" onClick={() => act(() => approveFiling(f.id))}>Add to folder</button>
              <button type="button" className="btn-ghost" onClick={() => act(() => skipFiling(f.id))}>Skip</button>
            </div>)}
          {BAD.has(f.state) && f.status === "staged" && <div className="stmt-actions"><button type="button" className="btn-ghost" onClick={() => act(() => skipFiling(f.id))}>Dismiss</button></div>}
        </div>
      ))}
      {ready.length > 1 && <button type="button" className="btn-primary" onClick={() => act(async () => { for (const f of ready) await approveFiling(f.id); })}>Add all {ready.length} new statements</button>}
    </section>
  );
}
