import { useCallback, useEffect, useRef, useState } from "react";
import { type ModelResult, type Scoreboard as SB, getGatewayStatus, getScoreboard, runScoreboard } from "../api";

const pct = (v: number | null) => (v === null ? "–" : `${Math.round(v * 100)}%`);

export default function Scoreboard() {
  const [sb, setSb] = useState<SB | null>(null);
  const [installed, setInstalled] = useState<string[]>([]);
  const [current, setCurrent] = useState("");
  const [picked, setPicked] = useState<Record<string, boolean>>({});
  const timer = useRef<number>();

  const load = useCallback(() => getScoreboard().then(setSb), []);
  useEffect(() => {
    load();
    getGatewayStatus().then((g) => {
      const names = g.local.installed.filter((n) => !n.includes("vision"));
      setInstalled(names); setCurrent(g.local.model);
      setPicked(Object.fromEntries(names.map((n) => [n, n === g.local.model || n.startsWith("qwen3.5") || n.startsWith("apertus")])));
    }).catch(() => undefined);
    return () => window.clearInterval(timer.current);
  }, [load]);
  useEffect(() => {
    window.clearInterval(timer.current);
    if (sb?.running) timer.current = window.setInterval(load, 5000);
  }, [sb?.running, load]);

  const chosen = installed.filter((n) => picked[n]);
  const start = async () => { await runScoreboard(chosen); load(); };
  const res = sb?.latest?.results;
  const best = res ? Math.max(...Object.values(res.models).map((m) => m.accuracy ?? -1)) : -1;
  const enough = (sb?.n_labelled ?? 0) >= 20 && (sb?.n_yes ?? 0) >= 4;

  return (
    <section className="card-box" aria-label="Model scoreboard">
      <h3>Model scoreboard</h3>
      <div className="note">Runs each model on the emails you have labelled (“This needs me” / “doesn't”) and shows how often it agrees with you. Local only.</div>
      <div><b>{sb?.n_labelled ?? 0}</b> emails labelled · <b>{sb?.n_yes ?? 0}</b> “needs me”.
        {!enough && <span className="muted"> Aim for at least 20 labelled, including a few that do need you, for a fair comparison.</span>}</div>
      <div className="models">
        {installed.map((n) => (
          <label key={n}><input type="checkbox" checked={!!picked[n]} onChange={(e) => setPicked({ ...picked, [n]: e.target.checked })} />
            <span className="mono">{n}</span>{n === current && <span className="chip chip-soft">in use</span>}</label>
        ))}
      </div>
      <button type="button" className="btn-small" onClick={start} disabled={sb?.running || chosen.length === 0 || (sb?.n_labelled ?? 0) === 0}>
        {sb?.running ? "Running… (a large model takes a few minutes)" : `Run scoreboard on ${chosen.length} model${chosen.length === 1 ? "" : "s"}`}
      </button>
      {sb?.latest?.status === "error" && <div className="note">The last run failed: {sb.latest.error}</div>}
      {res && (
        <>
          <table className="score">
            <thead><tr><th>model</th><th>agrees</th><th>missed</th><th>false alarms</th><th>sec/email</th></tr></thead>
            <tbody>
              {Object.entries(res.models).map(([name, m]: [string, ModelResult]) => (
                <tr key={name}><td>{name}</td><td className={m.accuracy === best ? "best" : ""}>{pct(m.accuracy)}</td><td>{m.fn}</td><td>{m.fp}</td>
                  <td>{m.seconds_per_email ?? "–"}</td></tr>
              ))}
            </tbody>
          </table>
          <div className="note">Tested on {res.n_model_cases} emails that reach the model.{res.rule_misses > 0 ? ` The simple rules wrongly skipped ${res.rule_misses} email(s) you marked as needing you.` : ""} “Missed” = it said no but you said yes. “False alarm” = it said yes but you said no.</div>
        </>
      )}
    </section>
  );
}
