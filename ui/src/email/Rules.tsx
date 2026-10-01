import { useCallback, useEffect, useState } from "react";
import { type Rule, addRule, deleteRule, getRules, redoTriage } from "../api";

export default function Rules() {
  const [rules, setRules] = useState<Rule[]>([]);
  const [text, setText] = useState("");
  const [note, setNote] = useState("");
  const load = useCallback(() => getRules().then((r) => setRules(r.items)), []);
  useEffect(() => { load(); }, [load]);

  const add = async () => {
    if (text.trim().length < 5) return;
    await addRule(text.trim()); setText(""); setNote("Rule saved. Use “Re-triage” to apply it to emails already judged."); load();
  };
  const redo = async () => { await redoTriage(); setNote("Re-triaging with your rules… the list updates as it goes."); };

  return (
    <section className="card-box" aria-label="Triage rules">
      <h3>Your triage rules</h3>
      <div className="note">Plain sentences the model must follow when deciding what needs you. For example: “Mail from the Geneva Hack list never needs a reply.”</div>
      {rules.map((r) => (
        <div key={r.id} className="rule"><span>{r.text}</span>
          <button type="button" aria-label="Remove rule" onClick={async () => { await deleteRule(r.id); load(); }}>✕</button></div>
      ))}
      <div className="add-row">
        <input value={text} onChange={(e) => setText(e.target.value)} placeholder="Add a rule…" maxLength={300}
          onKeyDown={(e) => e.key === "Enter" && add()} aria-label="New rule" />
        <button type="button" className="btn-small" onClick={add} disabled={text.trim().length < 5}>Add</button>
      </div>
      <button type="button" className="btn-ghost" onClick={redo}>Re-triage emails with these rules</button>
      {note && <div className="note">{note}</div>}
    </section>
  );
}
