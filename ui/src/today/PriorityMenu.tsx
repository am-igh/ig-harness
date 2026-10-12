import { useEffect, useRef, useState } from "react";
import { type Item, type PriorityTier, flagPriority } from "../api";

const OPTIONS: [PriorityTier, string, string][] = [
  ["red", "Top priority", "prio-dot-red"], ["orange", "High", "prio-dot-orange"], ["yellow", "Medium", "prio-dot-yellow"], ["none", "Normal (no colour)", "prio-dot-none"],
];

/** The flag on a to-do: set its priority yourself. What you choose always wins, and it teaches the harness which projects and kinds of item matter to you. */
export default function PriorityMenu({ it, onChanged }: { it: Item; onChanged: () => void }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const h = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false); };
    const k = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", h); document.addEventListener("keydown", k);
    return () => { document.removeEventListener("mousedown", h); document.removeEventListener("keydown", k); };
  }, [open]);
  const choose = async (t: PriorityTier) => { setOpen(false); try { await flagPriority(it.type, it.id, t); } finally { onChanged(); } };
  const p = it.priority;
  return (
    <div className="prio-wrap" ref={ref}>
      <button type="button" className={`prio-btn ${p?.pinned ? "pinned" : ""}`} onClick={() => setOpen((o) => !o)} aria-expanded={open} aria-label={`Priority of ${it.title}`} title="Set the priority yourself (this teaches the harness)">⚑</button>
      {open && (
        <div className="prio-menu" role="menu">
          <div className="prio-why"><b>Why it is where it is</b>{p?.reasons.map((r) => <div key={r}>· {r}</div>)}</div>
          {OPTIONS.map(([t, l, dot]) => <button key={t} type="button" role="menuitem" onClick={() => choose(t)}><i className={`prio-dot ${dot}`} />{l}{p?.pinned && p.tier === (t === "none" ? null : t) ? " ✓" : ""}</button>)}
          {p?.pinned && <button type="button" role="menuitem" className="prio-auto" onClick={() => choose("auto")}>Let the harness decide again</button>}
        </div>
      )}
    </div>
  );
}
