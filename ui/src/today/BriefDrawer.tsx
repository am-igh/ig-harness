import { useEffect, useState } from "react";
import { type Brief, type BriefDraftState, getBrief, getBriefDraft, saveBriefDraft, setBriefDraft } from "../api";
import { Shell } from "./Drawer";

/** The harness's own morning brief, in the order of her Claude brief, so the two can be compared. Rebuilding reads the current data again. */
export default function BriefDrawer({ onClose }: { onClose: () => void }) {
  const [b, setB] = useState<Brief | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(false);
  const load = (fresh: boolean) => { setBusy(true); getBrief(fresh).then((x) => { setB(x); setErr(false); }).catch(() => setErr(true)).finally(() => setBusy(false)); };
  const [d, setD] = useState<BriefDraftState | null>(null);
  const [msg, setMsg] = useState("");
  const loadDraft = () => getBriefDraft().then(setD).catch(() => setD(null));
  useEffect(() => { load(false); loadDraft(); const t = setInterval(loadDraft, 10_000); return () => clearInterval(t); }, []);
  const save = async () => { setMsg(""); try { await saveBriefDraft(); loadDraft(); } catch (e) { setMsg((e as Error).message); } };
  const status = !d ? "" : d.status === "saved" ? "Today's draft is in your Gmail drafts." : d.status === "queued" ? (d.agent_alive ? "Saving to Gmail…" : "Waiting for the draft agent (make agent-install).") : d.status === "failed" ? `Could not save: ${d.note ?? ""}` : "Not saved to Gmail yet today.";
  return (
    <Shell kicker="MORNING BRIEF" title={b?.text.split("\n")[0].replace("Morning brief by the IG Harness — ", "") ?? "Morning brief"} meta={b ? `Built ${b.created_at.slice(11, 16)} · section 5 by ${b.attention_source === "model" ? "your local model" : "plain rules"}` : "Building…"} onClose={onClose} wide>
      {err && <p className="muted">The brief could not be built just now.</p>}
      {b && <pre className="brief-text">{b.text.split("\n").slice(3).join("\n")}</pre>}
      <div className="brief-actions">
        <button type="button" className="btn-ghost" onClick={() => load(true)} disabled={busy}>{busy ? "Building…" : "Rebuild now"}</button>
        <button type="button" className="btn-primary" onClick={save} disabled={!d || d.status === "queued" || d.status === "saved"}>Save to Gmail now</button>
        <label className="phone-personal"><input type="checkbox" checked={d?.enabled ?? true} onChange={(e) => setBriefDraft(e.target.checked).then(loadDraft)} /> A draft in Gmail every morning at 08:00</label>
      </div>
      <div className="muted brief-status">{status} {msg}</div>
      <div className="muted brief-status">It is only ever a draft, to your own address, with “[Harness] Morning brief” in the subject. Search for that in Gmail. Nothing is sent.</div>
    </Shell>
  );
}
