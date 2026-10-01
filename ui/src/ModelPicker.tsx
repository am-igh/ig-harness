import { useCallback, useEffect, useRef, useState } from "react";
import { type ModelsInfo, getModels, selectModel } from "./api";

const SKIP = /vision|embed/i;   // not for text triage

export default function ModelPicker({ backendDown }: { backendDown: boolean }) {
  const [info, setInfo] = useState<ModelsInfo | null>(null);
  const [open, setOpen] = useState(false);
  const [msg, setMsg] = useState("");
  const box = useRef<HTMLDivElement>(null);

  const load = useCallback(() => getModels().then(setInfo).catch(() => setInfo(null)), []);
  useEffect(() => { load(); const t = setInterval(load, 30_000); return () => clearInterval(t); }, [load]);
  useEffect(() => {
    if (!open) return;
    load();
    const away = (e: MouseEvent) => { if (box.current && !box.current.contains(e.target as Node)) setOpen(false); };
    const esc = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", away); document.addEventListener("keydown", esc);
    return () => { document.removeEventListener("mousedown", away); document.removeEventListener("keydown", esc); };
  }, [open, load]);

  const job = info?.jobs[0];
  const ok = !backendDown && info?.local.up && job?.model_installed;
  const pick = async (jobKey: string, name: string) => {
    try {
      await selectModel(jobKey, "local", name);
      setMsg(jobKey === "email_draft" ? `Switched. New drafts will be written by ${name}.` : `Switched. New emails will be judged by ${name}. Use “Re-triage” on the Inbox tab to re-judge the ones already done.`);
      load();
    } catch { setMsg("That choice was refused."); }
  };

  return (
    <div className="picker" ref={box}>
      <button type="button" className="badge-model" onClick={() => setOpen((o) => !o)} aria-haspopup="dialog" aria-expanded={open}
        title="Choose which model does what">
        <i className={`dot ${backendDown ? "down" : ok ? "ok" : "warn"}`} />
        {backendDown ? "Back end not reachable" : !info?.local.up ? "Local model: off" : <>Model: <b>{job?.model ?? "…"}</b></>}
        <span className="caret">▾</span>
      </button>
      {open && info && job && (
        <div className="picker-pop" role="dialog" aria-label="Model picker">
          <div className="picker-head">Which model does what</div>

          {info.jobs.map((j) => (
            <div key={j.job} className="picker-job">
              <div className="picker-job-title"><b>{j.label}</b><span className="chip chip-personal">{j.tier} · local only</span></div>
              <div className="note">{j.job === "email_draft" ? "Drafts quote your correspondence, so only models running on this Mac can be chosen." : "Your emails are confidential, so only models running on this Mac can be chosen for this job."}</div>
              {info.local.models.filter((m) => !SKIP.test(m.name)).map((m) => (
                <label key={j.job + m.name} className={`opt ${m.name === j.model ? "sel" : ""}`}>
                  <input type="radio" name={`model-${j.job}`} checked={m.name === j.model} onChange={() => pick(j.job, m.name)} />
                  <span className="mono">{m.name}</span><span className="muted small">{m.size_gb} GB</span>
                  {m.name === j.model && <span className="chip chip-soft">in use</span>}
                </label>
              ))}
              {!j.model_installed && <div className="note">The chosen model “{j.model}” is not installed in Ollama.</div>}
            </div>
          ))}

          <div className="picker-ext">
            <div className="kicker">ONLINE MODELS · NOT SET UP YET</div>
            {info.external.map((e) => (
              <div key={e.provider} className="opt locked" title={e.note}>
                <span>🔒</span><span>{e.label}</span><span className="muted small">{e.hosting}</span>
                <span className="small tiers">{e.tiers.split(" (")[0]}</span>
              </div>
            ))}
            <div className="note">Online models need an API key in your Keychain and a secure route out of the harness (Phase 6). They would only ever be offered for jobs whose data is public or internal, and the gateway removes names, emails, IBANs and amounts first. This month: CHF {info.spend.toFixed(2)} of {info.cap_chf}.</div>
          </div>

          {msg && <div className="picker-msg">{msg}</div>}
        </div>
      )}
    </div>
  );
}
