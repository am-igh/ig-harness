"""Model scoreboard: run candidate local models on the emails Anne-Marie has labelled
("this needs me" / "doesn't need me") and report how often each one agrees with her.

Everything goes through the gateway to the local Ollama; nothing leaves the Mac. Results are
saved in model_evals. The models are judged on the emails that reach the model (the cheap
rules in triage.prefilter run first, as in real use); mistakes of those rules are reported separately."""
import json
import time
from datetime import datetime

from harness.config import now_local
from harness.gateway import Gateway
from harness.gateway.providers import OllamaProvider
from harness.triage import ask_model, prefilter


def labelled(conn):
    return conn.execute("SELECT * FROM emails WHERE user_label IS NOT NULL").fetchall()


def metrics(rows: list[tuple[bool, bool | None]]) -> dict:
    """rows = [(truth, predicted or None if the model failed)]"""
    ok = [(t, p) for t, p in rows if p is not None]
    tp = sum(t and p for t, p in ok); fp = sum((not t) and p for t, p in ok)
    fn = sum(t and (not p) for t, p in ok); tn = sum((not t) and (not p) for t, p in ok)
    n = len(ok)
    return {"n": n, "failed": len(rows) - n, "tp": tp, "fp": fp, "fn": fn, "tn": tn,
            "accuracy": round((tp + tn) / n, 3) if n else None,
            "precision": round(tp / (tp + fp), 3) if tp + fp else None,
            "recall": round(tp / (tp + fn), 3) if tp + fn else None}


def evaluate(conn, models: list[str], now: datetime | None = None, provider_factory=None) -> dict:
    now = now or now_local()
    rows = labelled(conn)
    skipped_by_rules = [r for r in rows if prefilter(r)]
    candidates = [r for r in rows if not prefilter(r)]
    rule_misses = sum(1 for r in skipped_by_rules if r["user_label"] == "yes")
    out = {"n_labelled": len(rows), "n_model_cases": len(candidates), "rule_misses": rule_misses, "models": {}}
    for m in models:
        gw = Gateway(providers={"local": (provider_factory or (lambda name: OllamaProvider(model=name)))(m)})
        results, times, load = [], [], None
        for e in candidates:
            t0 = time.time()
            parsed, _, _ = ask_model(conn, gw, e, now, purpose="model-scoreboard", job=None)   # job=None: test exactly this model, ignore the picker
            dt = time.time() - t0
            if load is None:
                load = round(dt, 1)           # first call includes loading the model into memory
            else:
                times.append(dt)
            results.append((e["user_label"] == "yes", None if parsed is None else parsed["needs_reply"]))
        res = metrics(results)
        res.update(seconds_per_email=round(sum(times) / len(times), 1) if times else None, first_call_seconds=load)
        out["models"][m] = res
    return out


def run_and_store(conn, models: list[str]) -> int:
    now = now_local()
    with conn:
        eid = conn.execute("INSERT INTO model_evals (started_at, n_labelled) VALUES (?,?)",
                           (now.isoformat(timespec="seconds"), len(labelled(conn)))).lastrowid
    try:
        res = evaluate(conn, models, now)
        status, err = "done", None
    except Exception as e:
        res, status, err = None, "error", f"{type(e).__name__}: {e}"
    with conn:
        conn.execute("UPDATE model_evals SET status=?, finished_at=?, results=?, error=? WHERE id=?",
                     (status, now_local().isoformat(timespec="seconds"), json.dumps(res) if res else None, err, eid))
    return eid


def latest(conn) -> dict | None:
    r = conn.execute("SELECT * FROM model_evals ORDER BY id DESC LIMIT 1").fetchone()
    if r is None:
        return None
    return {"id": r["id"], "status": r["status"], "started_at": r["started_at"], "finished_at": r["finished_at"],
            "error": r["error"], "results": json.loads(r["results"]) if r["results"] else None}
