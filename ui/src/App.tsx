import { useEffect, useState } from "react";
import { getMeta } from "./api";
import TodayTab from "./today/TodayTab";
import ProjectsTab from "./finance/ProjectsTab";
import EventsTab from "./events/EventsTab";
import ContractsTab from "./contracts/ContractsTab";
import InboxScene from "./scenes/InboxScene";
import EmailList from "./email/EmailList";
import ModelPicker from "./ModelPicker";
import RefreshChip from "./RefreshChip";
import Rules from "./email/Rules";
import WatchList from "./email/WatchList";
import Scoreboard from "./email/Scoreboard";
import StyleProfiles from "./email/StyleProfiles";

const TABS = [
  { id: "today", label: "Today" },
  { id: "inbox", label: "Inbox", phase: "Phase 2" },
  { id: "projects", label: "Projects & finance", phase: "Phase 4" },
  { id: "contracts", label: "Contracts & funders" },
  { id: "geneva", label: "Geneva and beyond", phase: "Phase 5" },
];

type Health = "checking" | "ok" | "down";

export default function App() {
  const [tab, setTab] = useState("today");
  const [health, setHealth] = useState<Health>("checking");
  const [demo, setDemo] = useState(false);
  useEffect(() => { getMeta().then((m) => setDemo(m.demo)).catch(() => {}); }, []);

  useEffect(() => {
    const check = () => {
      fetch("/api/health").then((r) => setHealth(r.ok ? "ok" : "down")).catch(() => setHealth("down"));
    };
    check();
    const t = setInterval(check, 30_000);
    return () => clearInterval(t);
  }, []);

  const current = TABS.find((t) => t.id === tab)!;
  return (
    <div className="app">
      {demo && <div className="demo-banner" role="note">DEMO · every name, amount and message on this screen is fictitious · not connected to any real data</div>}
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
        <RefreshChip />
        <ModelPicker backendDown={health === "down"} />
      </header>
      {tab === "today" ? <TodayTab /> : tab === "inbox" ? (
        <><InboxScene /><main className="page inbox-page"><section className="panel inbox"><div className="panel-head"><h2 className="serif">Inbox</h2></div><EmailList full /></section><div className="side-col"><StyleProfiles /><WatchList /><Rules /><Scoreboard /></div></main></>
      ) : tab === "projects" ? <ProjectsTab /> : tab === "contracts" ? <ContractsTab /> : tab === "geneva" ? <EventsTab /> : (
        <main className="page"><h2 className="serif">{current.label}</h2><p className="muted">Placeholder. Coming in {current.phase}.</p></main>
      )}
    </div>
  );
}
