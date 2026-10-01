import { useEffect, useState } from "react";
import TodayTab from "./today/TodayTab";
import EmailList from "./email/EmailList";

const TABS = [
  { id: "today", label: "Today" },
  { id: "inbox", label: "Inbox", phase: "Phase 2" },
  { id: "projects", label: "Projects & finance", phase: "Phase 4" },
  { id: "geneva", label: "Geneva", phase: "Phase 5" },
];

type Health = "checking" | "ok" | "down";
type Local = { up: boolean; model: string; model_installed: boolean } | null;

export default function App() {
  const [tab, setTab] = useState("today");
  const [health, setHealth] = useState<Health>("checking");
  const [local, setLocal] = useState<Local>(null);

  useEffect(() => {
    const check = () => {
      fetch("/api/health").then((r) => setHealth(r.ok ? "ok" : "down")).catch(() => setHealth("down"));
      fetch("/api/gateway/status").then((r) => r.json()).then((d) => setLocal(d.local)).catch(() => setLocal(null));
    };
    check();
    const t = setInterval(check, 30_000);
    return () => clearInterval(t);
  }, []);

  const current = TABS.find((t) => t.id === tab)!;
  return (
    <div className="app">
      <header className="top">
        <div className="brand">
          <img src="/ict4peace_logo.png" alt="ICT for Peace Foundation" />
          <span className="sep" />
          <span className="brand-text"><b>IG Harness</b><small>GENÈVE INTERNATIONALE</small></span>
        </div>
        <nav aria-label="Sections">
          {TABS.map((t) => (
            <button key={t.id} className={`tab ${t.id === tab ? "active" : ""}`} aria-current={t.id === tab ? "page" : undefined} onClick={() => setTab(t.id)}>{t.label}</button>
          ))}
        </nav>
        <div className="grow" />
        <div className="badge-lock">🔒 Drafts only · never sent automatically</div>
        <div className="badge-model" title={local ? `Model: ${local.model}${local.model_installed ? "" : " (not installed)"}` : ""}>
          <i className={`dot ${health === "down" ? "down" : local?.up && local.model_installed ? "ok" : "warn"}`} />
          {health === "down" ? "Back end not reachable" : local?.up && local.model_installed ? "Local model" : local?.up ? "Local model: not installed" : "Local model: off"}
        </div>
      </header>
      {tab === "today" ? <TodayTab /> : tab === "inbox" ? (
        <main className="page"><section className="panel inbox"><div className="panel-head"><h2 className="serif">Inbox</h2></div><EmailList full /></section></main>
      ) : (
        <main className="page"><h2 className="serif">{current.label}</h2><p className="muted">Placeholder. Coming in {current.phase}.</p></main>
      )}
    </div>
  );
}
