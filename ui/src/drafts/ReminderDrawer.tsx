import { useEffect, useState } from "react";
import { type ReminderThreads, getReminderThreads, makeReminderDraft } from "../api";
import { dayShort } from "../format";
import { Shell } from "../today/Drawer";
import DraftBox from "./DraftBox";

/** A reminder for something she is waiting on, drafted inside the conversation where she asked for it. */
export default function ReminderDrawer({ waitingId, onClose }: { waitingId: number; onClose: () => void }) {
  const [info, setInfo] = useState<ReminderThreads | null>(null);
  const [err, setErr] = useState("");
  const [choice, setChoice] = useState<string>("");   // thread id, or "new"
  useEffect(() => { getReminderThreads(waitingId).then((i) => { setInfo(i); setChoice(i.default_thread ?? "new"); }).catch((e) => setErr(e.message)); }, [waitingId]);

  return (
    <Shell kicker="REMINDER" title={info ? `Remind ${info.person}` : "Reminder"} meta={info ? `Waiting for: ${info.description}` : ""} onClose={onClose}>
      {err && <div className="edit-err">{err}</div>}
      {info && (
        <>
          <div className="related">
            <div className="kicker">WHICH CONVERSATION?</div>
            {info.threads.map((t) => (
              <label key={t.thread_id} className={`opt ${choice === t.thread_id ? "sel" : ""}`}>
                <input type="radio" name="thread" checked={choice === t.thread_id} onChange={() => setChoice(t.thread_id)} />
                <span style={{ flexGrow: 1 }}>{t.subject || "(no subject)"}</span>
                <span className="muted small">{dayShort(t.last_at.slice(0, 10))} · {t.last_from_me ? "you wrote last" : "they wrote last"}</span>
                {t.thread_id === info.default_thread && <span className="chip chip-soft">suggested</span>}
              </label>
            ))}
            <label className={`opt ${choice === "new" ? "sel" : ""}`}>
              <input type="radio" name="thread" checked={choice === "new"} onChange={() => setChoice("new")} />
              <span style={{ flexGrow: 1 }}>Start a new message</span>
            </label>
            {info.threads.length === 0 && <div className="note">No earlier conversation with {info.person} was found in what I read, so this would be a new message. (Run <span className="mono">make correspondence</span> to refresh.)</div>}
          </div>
          <DraftBox initial={null} startLabel="Draft the reminder"
            generate={(o) => makeReminderDraft(waitingId, { ...o, thread_id: choice === "new" ? null : choice, new_message: choice === "new" })} />
        </>
      )}
    </Shell>
  );
}
