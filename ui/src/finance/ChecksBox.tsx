import { useEffect, useState } from "react";
import { type ProjectChecks, getProjectChecks } from "../api";

const SEV: Record<string, string> = { error: "To fix", warning: "To check", info: "For information" };

/** The project checks (the harness's own controle_projets): evidence, dates, budget lines and mandate details. Read-only. */
export default function ChecksBox() {
  const [c, setC] = useState<ProjectChecks | null>(null);
  const [all, setAll] = useState(false);
  useEffect(() => { getProjectChecks().then(setC).catch(() => setC(null)); }, []);
  if (!c) return null;
  const shown = all ? c.findings : c.findings.filter((f) => f.severity !== "info");
  const info = c.findings.length - c.findings.filter((f) => f.severity !== "info").length;
  return (
    <section className="card-box" aria-label="Project checks">
      <div className="stmt-head"><h3>Project checks</h3>
        <span className={c.ok ? "stmt-ok" : "warn-text"}>{c.ok ? "No problems found" : `${c.counts.error} to fix · ${c.counts.warning} to check`}</span></div>
      <div className="note">Checked {c.checked.hours} hours entr{c.checked.hours === 1 ? "y" : "ies"}, {c.checked.costs} cost{c.checked.costs === 1 ? "" : "s"} and {c.checked.mandates} mandate{c.checked.mandates === 1 ? "" : "s"}. Costs and mandates are empty until you fill in costs.csv and the register.</div>
      {shown.map((f, i) => (
        <div key={i} className={`stmt-row ${f.severity === "error" ? "stmt-bad" : ""}`}>
          <div className="stmt-main"><span>{f.code ? <span className="mono">{f.code} · </span> : null}{f.message}{f.count > 1 ? ` (${f.count})` : ""}</span>
            {f.refs.length > 0 && <span className="stmt-detail">{f.refs.join(" · ")}</span>}</div>
          <span className="chip chip-soft">{SEV[f.severity]}</span>
        </div>
      ))}
      {info > 0 && <button type="button" className="btn-ghost" onClick={() => setAll(!all)}>{all ? "Hide" : "Show"} {info} note{info === 1 ? "" : "s"} for information</button>}
    </section>
  );
}
