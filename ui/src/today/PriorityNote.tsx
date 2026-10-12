import { useEffect, useState } from "react";
import { type PriorityStatus, getPriorityStatus, rerankPriority } from "../api";

/** One line under "Today & overdue": what the colours mean, and when the local model last ranked the list. */
export default function PriorityNote({ refreshKey }: { refreshKey: string }) {
  const [st, setSt] = useState<PriorityStatus | null>(null);
  const [asked, setAsked] = useState(false);
  useEffect(() => { getPriorityStatus().then(setSt).catch(() => setSt(null)); }, [refreshKey]);
  const when = st?.ranked_at ? new Date(st.ranked_at).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" }) : null;
  return (
    <div className="prio-note small muted">
      <span><i className="prio-dot prio-dot-red" /> most important overdue <i className="prio-dot prio-dot-orange" /> high <i className="prio-dot prio-dot-yellow" /> medium. Use ⚑ to set a priority yourself: the harness learns from it.</span>
      <span>{when ? `Ranked by ${st?.model ?? "the local model"} at ${when}` : "No model ranking yet (the colours come from rules)"}{st && st.feedback > 0 ? ` · learning from ${st.feedback} choice${st.feedback === 1 ? "" : "s"} of yours` : ""}
        {" "}<button type="button" className="link-quiet inline" disabled={asked} onClick={() => { setAsked(true); rerankPriority().finally(() => setTimeout(() => setAsked(false), 60000)); }}>{asked ? "Ranking…" : "Rank again"}</button></span>
    </div>
  );
}
