import { useCallback, useEffect, useState } from "react";

type Step = { name: string; state: string; note: string; seconds: number };
type Refresh = { state: "never" | "ok" | "running" | "stale" | "error"; label: string; problems: string[]; alive: boolean; steps?: Step[]; backup?: { last_ok_at: string; note: string } | null };

/** "Updated 07:32 ↻": when the harness last refreshed, and a button to do it now. */
export default function RefreshChip() {
  const [r, setR] = useState<Refresh | null>(null);
  const load = useCallback(() => fetch("/api/refresh/status").then((x) => x.json()).then(setR).catch(() => setR(null)), []);
  useEffect(() => { load(); }, [load]);
  useEffect(() => { const t = setInterval(load, r?.state === "running" ? 3000 : 15000); return () => clearInterval(t); }, [load, r?.state]);

  const now = async () => { await fetch("/api/refresh/now", { method: "POST" }); setR((p) => p && { ...p, state: "running", label: "Refreshing…" }); setTimeout(load, 1500); };
  if (!r) return null;
  const tip = [
    r.alive ? "Auto-refresh is on (every 30 min, 06:30–21:00)." : "Auto-refresh is OFF. On your Mac run: make refresh-install",
    ...(r.steps ?? []).map((s) => `${s.name}: ${s.state}${s.note ? " · " + s.note : ""}`),
  ].join("\n");
  const dot = r.state === "ok" ? "ok" : r.state === "running" ? "run" : "warn";
  return (
    <button type="button" className="refresh-chip" onClick={now} disabled={r.state === "running"} title={tip}
      aria-label={`${r.label}. Press to refresh now.`}>
      <i className={`dot ${dot}`} />{r.label}{!r.alive && " · auto-refresh off"}<span className={`spin ${r.state === "running" ? "on" : ""}`}>↻</span>
    </button>
  );
}
