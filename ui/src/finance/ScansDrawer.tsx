import { useCallback, useEffect, useRef, useState } from "react";
import { type Scan, approveScan, editScan, getScans, skipScan, splitScan, uploadScan } from "../api";
import { Shell } from "../today/Drawer";

const TYPES: [string, string][] = [["invoice_received", "Invoice received"], ["receipt", "Receipt"], ["invoice_issued", "Invoice issued by ICT4Peace"], ["contract", "Contract"], ["other", "Other document"]];

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return <label className="scan-field"><span>{label}</span>{children}</label>;
}

function ScanCard({ s, onChange }: { s: Scan; onChange: (s: Scan) => void }) {
  const [draft, setDraft] = useState<Record<string, string>>({});
  const [err, setErr] = useState("");
  useEffect(() => { setDraft({}); }, [s.id, s.status]);
  const val = (k: keyof Scan) => (draft[k] ?? (s[k] == null ? "" : String(s[k])));
  const set = (k: string, v: string) => setDraft((d) => ({ ...d, [k]: v }));
  const save = async (k: string) => {
    if (draft[k] === undefined || draft[k] === String(s[k as keyof Scan] ?? "")) return;
    setErr("");
    try { onChange(await editScan(s.id, { [k]: draft[k] === "" ? null : draft[k] })); } catch (e) { setErr((e as Error).message); }
  };
  const pick = async (k: string, v: string) => { setErr(""); try { onChange(await editScan(s.id, { [k]: v === "" ? null : v })); } catch (e) { setErr((e as Error).message); } };
  const act = async (fn: () => Promise<Scan>) => { setErr(""); try { onChange(await fn()); } catch (e) { setErr((e as Error).message); } };
  const open = s.status === "proposed" || s.status === "duplicate";
  return (
    <div className={`scan-card ${s.status === "duplicate" || s.status === "failed" ? "stmt-bad" : ""}`}>
      <div className="scan-head"><span className="mono stmt-name">{s.original_name}{s.pages && s.pages > 1 ? ` · ${s.pages} pages` : ""}</span><span className="chip chip-soft">{({ found: "Waiting", reading: "Reading…", proposed: "To confirm", duplicate: "Duplicate", approved: "Filing…", filed: "Filed", failed: "Not filed", unreadable: "Cannot read", skipped: "Skipped" } as Record<string, string>)[s.status]}</span></div>
      {(s.status === "found" || s.status === "reading") && <p className="muted">Reading this scan on your Mac…</p>}
      {open && (
        <>
          <div className="scan-fields">
            <Field label="Type"><select value={s.doc_type ?? ""} onChange={(e) => pick("doc_type", e.target.value)}><option value="">Choose…</option>{TYPES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select></Field>
            <Field label="Supplier / customer"><input value={val("supplier")} onChange={(e) => set("supplier", e.target.value)} onBlur={() => save("supplier")} /></Field>
            <Field label="Number"><input value={val("number")} onChange={(e) => set("number", e.target.value)} onBlur={() => save("number")} /></Field>
            <Field label="Amount"><input value={val("amount")} inputMode="decimal" onChange={(e) => set("amount", e.target.value)} onBlur={() => save("amount")} /></Field>
            <Field label="Currency"><select value={s.currency ?? ""} onChange={(e) => pick("currency", e.target.value)}><option value="">–</option>{["CHF", "EUR", "USD", "GBP"].map((c) => <option key={c}>{c}</option>)}</select></Field>
            <Field label="Payment date"><input value={val("paid_date")} placeholder="2026-09-30" onChange={(e) => set("paid_date", e.target.value)} onBlur={() => save("paid_date")} /></Field>
            <Field label="Folder"><select value={s.folder ?? ""} onChange={(e) => pick("folder", e.target.value)}><option value="">Choose…</option><option>Expenses</option><option>Income</option></select></Field>
          </div>
          <div className="scan-name">{s.proposed_name ? <><span className="muted">Will be saved as</span> <span className="mono">{s.year}/{s.folder}/{s.proposed_name}</span></> : <span className="warn-text">No file name yet</span>}</div>
          {s.note && <div className="stmt-detail">{s.note}</div>}
          <div className="stmt-actions">
            <button type="button" className="btn-primary" disabled={!s.proposed_name || s.status !== "proposed"} onClick={() => act(() => approveScan(s.id))}>Add to folder</button>
            <button type="button" className="btn-ghost" onClick={() => act(() => skipScan(s.id))}>{s.status === "duplicate" ? "Dismiss" : "Skip"}</button>
            {(s.pages ?? 1) > 1 && s.status === "proposed" && <button type="button" className="btn-ghost" title="Use this when the pages are different documents" onClick={() => act(async () => { await splitScan(s.id); return s; })}>Split into single pages</button>}
          </div>
        </>
      )}
      {s.status === "approved" && <span className="soon">Adding to your folder…</span>}
      {s.status === "filed" && <span className="stmt-ok">✓ Added as {s.year}/{s.folder}/{s.proposed_name}. The original scan stays in Scan-Inbox; you can tidy it when you like.</span>}
      {s.status === "failed" && <span className="warn-text">Not filed: {s.result}</span>}
      {s.status === "unreadable" && <span className="stmt-detail">{s.note}</span>}
      {err && <div className="edit-err">{err}</div>}
    </div>
  );
}

export function useScans() {
  const [data, setData] = useState<{ items: Scan[]; summary: import("../api").ScanSummary } | null>(null);
  const load = useCallback(() => getScans().then(setData).catch(() => setData(null)), []);
  useEffect(() => { load(); }, [load]);
  const busy = !!data && (data.summary.reading > 0 || data.summary.approved > 0);
  useEffect(() => { const t = setInterval(load, busy ? 3000 : 15000); return () => clearInterval(t); }, [load, busy]);
  return { data, reload: load };
}

export default function ScansDrawer({ onClose, onChanged }: { onClose: () => void; onChanged: () => void }) {
  const { data, reload } = useScans();
  const [err, setErr] = useState("");
  const input = useRef<HTMLInputElement>(null);
  const prevFiled = useRef(0);
  useEffect(() => { const n = data?.summary.filed_this_week ?? 0; if (n > prevFiled.current && prevFiled.current > 0) onChanged(); prevFiled.current = n; }, [data, onChanged]);
  const pick = async (files: FileList | null) => {
    if (!files?.length) return;
    setErr("");
    for (const f of Array.from(files)) { try { await uploadScan(f); } catch (e) { setErr(`${f.name}: ${(e as Error).message}`); } }
    if (input.current) input.current.value = ""; reload();
  };
  const items = (data?.items ?? []);
  const patch = (s: Scan) => { reload(); void s; };
  const ready = items.filter((s) => s.status === "proposed" && s.proposed_name);
  return (
    <Shell kicker="INVOICES AND RECEIPTS" title={data?.summary.to_confirm ? `${data.summary.to_confirm} to confirm` : "Invoices and receipts"} meta="Scans are read on this Mac only. Nothing is filed until you approve it." onClose={onClose} wide>
      <div className="stmt-head"><span className="muted">Scans saved in Scan-Inbox appear here by themselves.</span>
        <button type="button" className="btn-small" onClick={() => input.current?.click()}>Add invoices and receipts</button>
        <input ref={input} type="file" accept="application/pdf,.pdf" multiple hidden onChange={(e) => pick(e.target.files)} /></div>
      {err && <div className="edit-err">{err}</div>}
      {items.length === 0 && <p className="muted">Nothing here yet. Scan a document with Image Capture, or choose a PDF with the button.</p>}
      {items.map((s) => <ScanCard key={s.id} s={s} onChange={patch} />)}
      {ready.length > 1 && <button type="button" className="btn-primary" onClick={async () => { for (const s of ready) { try { await approveScan(s.id); } catch { /* shown on its card */ } } reload(); }}>Add all {ready.length} to folder</button>}
    </Shell>
  );
}
