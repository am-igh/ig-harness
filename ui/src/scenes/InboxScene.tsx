import { useEffect, useState } from "react";
import { type EmailsResponse, getEmails } from "../api";
import { todayIso } from "../format";
import Scene, { type SceneMark } from "./Scene";

/** The harbour: the lighthouse watches the emails that need you; the ones with a deadline are boats on the water. */
export default function InboxScene() {
  const [d, setD] = useState<EmailsResponse | null>(null);
  useEffect(() => { getEmails(72, false).then(setD).catch(() => setD(null)); }, []);
  const today = todayIso();
  const open = (d?.needs_reply ?? []).filter((e) => !e.handled_at);
  const dated = open.filter((e) => e.deadline && e.deadline >= today);
  const marks: SceneMark[] = dated.map((e) => ({ id: String(e.id), label: e.subject || "(no subject)", date: e.deadline!, tone: (e.urgency ?? 1) >= 3 ? "major" : "normal", title: `${e.from_name || e.from_email}: ${e.subject}` }));
  const undated = open.length - dated.length;
  return (
    <Scene variant="harbor" today={today} kicker="THE HARBOUR" headline="Inbox" sub={open.length ? `${undated} at anchor without a date` : "Calm water"}
      stat={{ value: open.length, label: "need you", hint: "the lighthouse is watching" }} marks={marks} minSpan={21} maxSpan={60}
      legend={[{ color: "#E8A300", label: "urgent deadline" }, { color: "#AEB9E8", label: "reply by" }]} empty={open.length ? "No reply deadlines yet; the boats stay at anchor." : undefined} />
  );
}
