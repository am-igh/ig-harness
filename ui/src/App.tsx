import { useEffect, useState } from "react";
import TodayTab from "./today/TodayTab";

const TABS = [
  { id: "today", label: "Today" },
  { id: "inbox", label: "Inbox", phase: "Phase 2" },
  { id: "projects", label: "Projects & finance", phase: "Phase 4" },
  { id: "geneva", label: "Geneva", phase: "Phase 5" },
];

type Health = "checking" | "ok" | "down";

export default function App() {
  const [tab, setTab] = useState("today");
  const [health, setHealth] = useState<Health>("checking");

  useEffect(() => {
    const check = () => fetch("/api/health").then((r) => setHealth(r.ok ? "ok" : "down")).catch(() => setHealth("down"));
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
        <div className="badge-model"><i className={`dot ${health}`} />{health === "ok" ? "Harness running" : health === "down" ? "Back end not reachable" : "Checking…"}</div>
      </header>
      {tab === "today" ? <TodayTab /> : (
        <main className="page"><h2 className="serif">{current.label}</h2><p className="muted">Placeholder. Coming in {current.phase}.</p></main>
      )}
    </div>
  );
}
