import { useEffect, useState } from "react";

const TABS = [
  { id: "today", label: "Today", phase: "Phase 1, task 4" },
  { id: "inbox", label: "Inbox", phase: "Phase 2" },
  { id: "projects", label: "Projects & finance", phase: "Phase 4" },
  { id: "geneva", label: "Geneva", phase: "Phase 5" },
];

type Health = "checking" | "ok" | "down";

export default function App() {
  const [tab, setTab] = useState("today");
  const [health, setHealth] = useState<Health>("checking");

  useEffect(() => {
    fetch("/api/health")
      .then((r) => (r.ok ? setHealth("ok") : setHealth("down")))
      .catch(() => setHealth("down"));
  }, []);

  const current = TABS.find((t) => t.id === tab)!;
  const status = { checking: "Checking…", ok: "Connected", down: "Back end not reachable" }[health];

  return (
    <>
      <header className="top">
        <h1>IG Harness</h1>
        <nav>
          {TABS.map((t) => (
            <button key={t.id} className={t.id === tab ? "active" : ""} onClick={() => setTab(t.id)}>
              {t.label}
            </button>
          ))}
        </nav>
        <span className={`status ${health}`}>{status}</span>
      </header>
      <main>
        <h2>{current.label}</h2>
        <p>Placeholder. Coming in {current.phase}.</p>
      </main>
    </>
  );
}
