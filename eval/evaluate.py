"""Evaluate detection and redaction on the synthetic test set.

Compares the three detection modes (rules, ner, hybrid) and reports:
  - precision, recall and F1 per entity type (a prediction counts as correct
    if it overlaps a ground-truth item of the same type)
  - leakage rate: share of ground-truth values still present verbatim in the
    redacted prompt (the privacy outcome that matters most)
  - false alarms on prompts that contain no personal information
  - name recall by name origin (bias check)
  - average processing time per prompt

    python eval/evaluate.py                       # all modes, default threshold
    python eval/evaluate.py --modes hybrid --threshold 0.3
"""
import argparse
import csv
import json
import statistics
import sys
import time
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from detector import ENTITIES, MODES, apply, detect  # noqa: E402


def overlaps(a, b):
    return a["start"] < b["end"] and b["start"] < a["end"]


def prf(tp, fp, fn):
    p = tp / (tp + fp) if tp + fp else float("nan")
    r = tp / (tp + fn) if tp + fn else float("nan")
    f = 2 * p * r / (p + r) if p == p and r == r and p + r else float("nan")
    return p, r, f


def fmt(x):
    return "–" if x != x else f"{x:.2f}"


def evaluate(rows, mode, threshold):
    counts = {e: {"tp": 0, "fp": 0, "fn": 0} for e in ENTITIES}
    leaked, total_gold = 0, 0
    leaked_by_type = defaultdict(lambda: [0, 0])
    neg_prompts, neg_flagged, neg_fp = 0, 0, 0
    origin = defaultdict(lambda: [0, 0])  # origin -> [found, total]
    times, misses, false_alarms = [], [], []
    by_type = defaultdict(lambda: {"found": 0, "gold": 0, "leaked": 0})  # per prompt type

    for row in rows:
        text, gold = row["text"], row["entities"]
        t0 = time.perf_counter()
        dets = detect(text, mode=mode, threshold=threshold)
        preds = [d.to_dict() for d in dets]
        times.append((time.perf_counter() - t0) * 1000)

        matched_pred = set()
        for g in gold:
            hit = [i for i, p in enumerate(preds) if p["entity"] == g["type"] and overlaps(p, g)]
            if hit:
                counts[g["type"]]["tp"] += 1
                matched_pred.update(hit)
                by_type[row["category"]]["found"] += 1
            else:
                counts[g["type"]]["fn"] += 1
                misses.append({"id": row["id"], "type": g["type"], "value": g["value"]})
            if g["type"] == "PERSON":
                origin[g["meta"].get("origin", "?")][0] += bool(hit)
                origin[g["meta"].get("origin", "?")][1] += 1
        for i, p in enumerate(preds):
            if i not in matched_pred:
                counts[p["entity"]]["fp"] += 1
                false_alarms.append({"id": row["id"], "type": p["entity"], "value": p["text"]})

        # leakage: is the original value still visible after redaction?
        red = apply(text, dets, method="redact")["text"]
        for g in gold:
            total_gold += 1
            leaked_by_type[g["type"]][1] += 1
            by_type[row["category"]]["gold"] += 1
            if g["value"] in red:
                leaked += 1
                by_type[row["category"]]["leaked"] += 1
                leaked_by_type[g["type"]][0] += 1

        if row["category"] == "negative":
            neg_prompts += 1
            neg_flagged += bool(preds)
            neg_fp += len(preds)

    tp = sum(c["tp"] for c in counts.values())
    fp = sum(c["fp"] for c in counts.values())
    fn = sum(c["fn"] for c in counts.values())
    return {
        "mode": mode,
        "threshold": threshold,
        "per_entity": {e: {**c, **dict(zip(("precision", "recall", "f1"), prf(**c)))} for e, c in counts.items()},
        "overall": dict(zip(("precision", "recall", "f1"), prf(tp, fp, fn))) | {"tp": tp, "fp": fp, "fn": fn},
        "leakage_rate": leaked / total_gold if total_gold else 0.0,
        "leakage_by_type": {k: v[0] / v[1] for k, v in leaked_by_type.items()},
        "negative_prompts": neg_prompts,
        "negative_prompts_flagged": neg_flagged,
        "negative_false_positives": neg_fp,
        "name_recall_by_origin": {k: (v[0] / v[1], v[1]) for k, v in sorted(origin.items())},
        "ms_per_prompt_median": statistics.median(times),
        "by_prompt_type": {k: dict(v) for k, v in sorted(by_type.items())},
        "misses": misses,
        "false_alarms": false_alarms,
    }


def write_report(results, n_prompts, n_gold, out_dir: Path):
    out_dir.mkdir(parents=True, exist_ok=True)
    L = [f"# Evaluation results\n", f"Synthetic test set: {n_prompts} prompts, {n_gold} labelled items. Threshold: {results[0]['threshold']}.\n"]

    L.append("## Overall by detection mode\n")
    L.append("| Mode | Precision | Recall | F1 | Leakage rate | False alarms on clean prompts | ms / prompt |")
    L.append("|---|---|---|---|---|---|---|")
    for r in results:
        o = r["overall"]
        L.append(f"| {r['mode']} | {fmt(o['precision'])} | {fmt(o['recall'])} | {fmt(o['f1'])} | {r['leakage_rate']:.1%} | "
                 f"{r['negative_prompts_flagged']}/{r['negative_prompts']} prompts ({r['negative_false_positives']} items) | {r['ms_per_prompt_median']:.0f} |")

    L.append("\n## Recall by entity type\n")
    L.append("| Entity | " + " | ".join(r["mode"] for r in results) + " |")
    L.append("|---|" + "---|" * len(results))
    for e in ENTITIES:
        L.append(f"| {e} | " + " | ".join(fmt(r["per_entity"][e]["recall"]) for r in results) + " |")

    L.append("\n## Precision by entity type\n")
    L.append("| Entity | " + " | ".join(r["mode"] for r in results) + " |")
    L.append("|---|" + "---|" * len(results))
    for e in ENTITIES:
        L.append(f"| {e} | " + " | ".join(fmt(r["per_entity"][e]["precision"]) for r in results) + " |")

    L.append("\n## Recall and leakage by prompt type\n")
    L.append("| Prompt type | " + " | ".join(f"{r['mode']} recall | {r['mode']} leakage" for r in results) + " |")
    L.append("|---|" + "---|---|" * len(results))
    for cat in results[0]["by_prompt_type"]:
        cells = []
        for r in results:
            b = r["by_prompt_type"][cat]
            cells.append(f"{b['found'] / b['gold']:.2f} | {b['leaked'] / b['gold']:.1%}")
        L.append(f"| {cat} | " + " | ".join(cells) + " |")

    for r in results:
        if r["name_recall_by_origin"]:
            L.append(f"\n## Name recall by name origin ({r['mode']})\n")
            L.append("| Name origin | Recall | Names |")
            L.append("|---|---|---|")
            for k, (rec, n) in r["name_recall_by_origin"].items():
                L.append(f"| {k} | {rec:.2f} | {n} |")

    best = max(results, key=lambda r: r["overall"]["recall"])
    L.append(f"\n## Sample misses ({best['mode']})\n")
    for m in best["misses"][:15]:
        L.append(f"- `{m['type']}` {m['value']!r} (prompt {m['id']})")
    L.append(f"\n## Sample false alarms ({best['mode']})\n")
    for m in best["false_alarms"][:15]:
        L.append(f"- `{m['type']}` {m['value']!r} (prompt {m['id']})")

    (out_dir / "report.md").write_text("\n".join(L) + "\n", encoding="utf-8")

    with open(out_dir / "per_entity.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["mode", "entity", "tp", "fp", "fn", "precision", "recall", "f1"])
        for r in results:
            for e, c in r["per_entity"].items():
                w.writerow([r["mode"], e, c["tp"], c["fp"], c["fn"]] + [round(c[k], 4) if c[k] == c[k] else "" for k in ("precision", "recall", "f1")])
    (out_dir / "results.json").write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=str(ROOT / "eval" / "data" / "test_set.jsonl"))
    ap.add_argument("--modes", nargs="+", default=list(MODES), choices=MODES)
    ap.add_argument("--threshold", type=float, default=0.4)
    ap.add_argument("--out", default=str(ROOT / "eval" / "results"))
    args = ap.parse_args()

    rows = [json.loads(l) for l in open(args.data, encoding="utf-8")]
    n_gold = sum(len(r["entities"]) for r in rows)
    results = []
    for mode in args.modes:
        print(f"Evaluating {mode} on {len(rows)} prompts ...", flush=True)
        results.append(evaluate(rows, mode, args.threshold))
    write_report(results, len(rows), n_gold, Path(args.out))
    print((Path(args.out) / "report.md").read_text())


if __name__ == "__main__":
    main()
