import { useEffect, useState } from "react";
import { type Brief, getBrief } from "../api";
import { Shell } from "./Drawer";

/** The harness's own morning brief, in the order of her Claude brief, so the two can be compared. Rebuilding reads the current data again. */
export default function BriefDrawer({ onClose }: { onClose: () => void }) {
  const [b, setB] = useState<Brief | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(false);
  const load = (fresh: boolean) => { setBusy(true); getBrief(fresh).then((x) => { setB(x); setErr(false); }).catch(() => setErr(true)).finally(() => setBusy(false)); };
  useEffect(() => load(false), []);
  return (
    <Shell kicker="MORNING BRIEF" title={b?.text.split("\n")[0].replace("Morning brief by the IG Harness — ", "") ?? "Morning brief"} meta={b ? `Built ${b.created_at.slice(11, 16)} · section 5 by ${b.attention_source === "model" ? "your local model" : "plain rules"}` : "Building…"} onClose={onClose} wide>
      {err && <p className="muted">The brief could not be built just now.</p>}
      {b && <pre className="brief-text">{b.text.split("\n").slice(3).join("\n")}</pre>}
      <button type="button" className="btn-ghost" onClick={() => load(true)} disabled={busy}>{busy ? "Building…" : "Rebuild now"}</button>
    </Shell>
  );
}
