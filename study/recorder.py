"""Study mode for the user evaluation (only active with `python app.py --study`).

Records one row per completed task in study_data/sessions.csv. It stores
counts, timings and choices only: never the prompt text, the protected text
or anything the participant typed. The protected text is used once, in
memory, to count which known personal details are still visible, and is then
discarded.
"""
import csv
import json
import threading
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TASKS = json.loads((Path(__file__).parent / "tasks.json").read_text(encoding="utf-8"))["tasks"]
TASKS_BY_ID = {t["id"]: t for t in TASKS}
DATA_DIR = ROOT / "study_data"
CSV_PATH = DATA_DIR / "sessions.csv"
_lock = threading.Lock()

FIELDS = [
    "recorded_at", "participant", "task", "assigned_method", "method_used",
    "seconds_total", "seconds_review", "checks",
    "n_detected", "n_unticked", "n_added", "added_types",
    "n_gold", "n_exposed", "exposed_types", "planted_protected",
    "copied", "restore_used",
]


def assigned_method(participant: str, task_id: str) -> str:
    """Counterbalance: odd participants pseudonymize T1 and redact T2; even ones the reverse."""
    task = TASKS_BY_ID[task_id]
    if task["method"] != "assigned":
        return "choice"
    digits = "".join(c for c in participant if c.isdigit())
    odd = int(digits or "1") % 2 == 1
    first, second = ("pseudonymize", "redact") if odd else ("redact", "pseudonymize")
    return first if task_id == "T1" else second


def public_tasks(participant: str):
    """What the browser may see: no gold labels, no hints about planted items."""
    return [{"id": t["id"], "title": t["title"], "instructions": t["instructions"], "prompt": t["prompt"],
             "method": assigned_method(participant, t["id"])} for t in TASKS]


def record(data: dict) -> dict:
    task = TASKS_BY_ID[data["task"]]
    final_text = data.get("final_text", "")
    exposed = [g for g in task["gold"] if g["value"] in final_text]
    planted = [g for g in task["gold"] if g.get("planted")]
    row = {
        "recorded_at": datetime.now().isoformat(timespec="seconds"),
        "participant": str(data.get("participant", ""))[:20],
        "task": task["id"],
        "assigned_method": assigned_method(str(data.get("participant", "")), task["id"]),
        "method_used": data.get("method_used", ""),
        "seconds_total": round(float(data.get("seconds_total", 0)), 1),
        "seconds_review": round(float(data.get("seconds_review", 0)), 1),
        "checks": int(data.get("checks", 0)),
        "n_detected": int(data.get("n_detected", 0)),
        "n_unticked": int(data.get("n_unticked", 0)),
        "n_added": int(data.get("n_added", 0)),
        "added_types": ";".join(sorted(set(map(str, data.get("added_types", []))))),
        "n_gold": len(task["gold"]),
        "n_exposed": len(exposed),
        "exposed_types": ";".join(sorted({g["type"] for g in exposed})),
        "planted_protected": int(all(g["value"] not in final_text for g in planted)) if planted else "",
        "copied": int(bool(data.get("copied"))),
        "restore_used": int(bool(data.get("restore_used"))),
    }
    del final_text  # never stored
    with _lock:
        DATA_DIR.mkdir(exist_ok=True)
        new = not CSV_PATH.exists()
        with open(CSV_PATH, "a", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=FIELDS)
            if new:
                w.writeheader()
            w.writerow(row)
    return {"saved": True, "exposed": len(exposed)}
