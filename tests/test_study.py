"""Tests for study mode. Run with:  python -m pytest -q"""
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from study import recorder  # noqa: E402


def test_counterbalancing():
    assert recorder.assigned_method("P01", "T1") == "pseudonymize"
    assert recorder.assigned_method("P01", "T2") == "redact"
    assert recorder.assigned_method("P02", "T1") == "redact"
    assert recorder.assigned_method("P02", "T2") == "pseudonymize"
    assert recorder.assigned_method("P02", "T3") == "choice"


def test_browser_never_sees_gold_labels():
    for t in recorder.public_tasks("P01"):
        assert "gold" not in t and "planted" not in str(t)


def test_record_stores_no_text_and_counts_exposed(tmp_path, monkeypatch):
    monkeypatch.setattr(recorder, "DATA_DIR", tmp_path)
    monkeypatch.setattr(recorder, "CSV_PATH", tmp_path / "sessions.csv")
    task = recorder.TASKS_BY_ID["T1"]
    final = task["prompt"].replace("Karen Liu", "[PERSON_1]")  # everything else still visible
    out = recorder.record({"participant": "P03", "task": "T1", "method_used": "pseudonymize", "final_text": final})
    assert out["exposed"] == len(task["gold"]) - 1
    raw = (tmp_path / "sessions.csv").read_text(encoding="utf-8")
    for g in task["gold"]:
        assert g["value"] not in raw  # no personal details or prompt text in the file
    row = next(csv.DictReader(open(tmp_path / "sessions.csv", encoding="utf-8")))
    assert row["planted_protected"] == "0"
