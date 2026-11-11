"""Privacy side of the comparison: full redaction vs pseudonymization.

Detection is shared, so this isolates what the TRANSFORMATION changes. Every
measure is computed twice (proposal, Phase 4):
  - "gold":   ground-truth labels, i.e. perfect detection (isolates the method)
  - "hybrid": the pipeline's actual detections (what users get; shows the
              effect of detection errors)

Measures:
  - residual leakage: share of real values still visible in the prompt the AI
    receives, overall, by prompt type and by entity type
  - what each format still reveals: the type of each item, how many distinct
    people there are, and which mentions refer to the same person
  - people kept apart: in prompts with 2+ people, can the AI still tell them apart?
  - restore success: if the AI repeated the transformed prompt, would restoring
    give back the original exactly?

The optional "surrogate" condition (realistic fake values) can be added with
--methods redact pseudonymize surrogate.

    python eval/compare_methods.py
"""
import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from detector import Detection, apply, detect, restore  # noqa: E402
from detector.engine import _normalize  # noqa: E402

LABEL = {"redact": "Full redaction", "pseudonymize": "Pseudonymization", "surrogate": "Surrogates (extra)"}
PLACEHOLDER = re.compile(r"\[([A-Z_]+?)_(\d+)\]")


def key(d):
    return (d.entity, _normalize(d.entity, d.text))


def analyse(row, dets, method):
    """Per-prompt measures for one method."""
    text, gold = row["text"], row["entities"]
    out = apply(text, dets, method=method, seed=row["id"])
    sent, mapping = out["text"], out["mapping"]
    inv = defaultdict(set)  # real value -> what the AI saw
    for fake, real in mapping.items():
        inv[real].add(fake)

    def replacement(d):
        if method == "redact":
            return "[REDACTED]"
        return next(iter(sorted(inv.get(d.text, {None}), key=lambda x: -len(x or ""))), None)

    reps = [(d, replacement(d)) for d in dets]
    m = {"leaked": [(g["type"], g["value"] in sent) for g in gold]}

    # 1. Type of each item: readable from the replacement?
    if method == "redact":
        m["type_revealed"] = [False for _ in reps]
    elif method == "pseudonymize":
        m["type_revealed"] = [bool(r and PLACEHOLDER.fullmatch(r)) for _, r in reps]
    else:  # realistic surrogates carry their type in their format
        m["type_revealed"] = [r is not None for _, r in reps]

    # 2. + 3. Distinct people and same-person links (co-reference)
    persons = [(d, r) for d, r in reps if d.entity == "PERSON"]
    real_people = {key(d) for d, _ in persons}
    seen_people = {r for _, r in persons if r}
    m["n_people"] = len(real_people)
    m["people_count_revealed"] = (method != "redact") and len(seen_people) == len(real_people) and len(real_people) > 0
    by_person = defaultdict(set)
    for d, r in persons:
        by_person[key(d)].add(r)
    repeated = [k for k in by_person if sum(1 for d, _ in persons if key(d) == k) > 1]
    m["repeated_people"] = len(repeated)
    m["links_revealed"] = 0 if method == "redact" else sum(1 for k in repeated if len(by_person[k]) == 1)

    # People kept apart: gold people, judged on what the AI received
    gold_people = {_normalize("PERSON", g["value"]) for g in gold if g["type"] == "PERSON"}
    if len(gold_people) >= 2:
        if method == "redact":
            m["kept_apart"] = False
        else:
            reps_gold = {}
            for g in gold:
                if g["type"] == "PERSON":
                    hit = [r for d, r in reps if d.entity == "PERSON" and d.start < g["end"] and g["start"] < d.end]
                    reps_gold[_normalize("PERSON", g["value"])] = hit[0] if hit else g["value"]  # missed = real name
            m["kept_apart"] = len(set(reps_gold.values())) == len(gold_people)

    if dets:
        m["restored"] = restore(sent, mapping) == text
    return m


def summarise(rows, source, methods, threshold):
    res = {}
    for method in methods:
        agg = defaultdict(lambda: [0, 0])
        for row in rows:
            dets = ([Detection(g["type"], g["start"], g["end"], g["value"], 1.0, "gold") for g in row["entities"]]
                    if source == "gold" else detect(row["text"], mode="hybrid", threshold=threshold))
            m = analyse(row, dets, method)
            for ent, leaked in m["leaked"]:
                for k in ("leak", f"leak_ent:{ent}", f"leak_type:{row['category']}"):
                    agg[k][0] += leaked
                    agg[k][1] += 1
            agg["type"][0] += sum(m["type_revealed"])
            agg["type"][1] += len(m["type_revealed"])
            if m["n_people"]:
                agg["count"][0] += m["people_count_revealed"]
                agg["count"][1] += 1
            agg["links"][0] += m["links_revealed"]
            agg["links"][1] += m["repeated_people"]
            if "kept_apart" in m:
                for k in ("apart", f"apart_type:{row['category']}"):
                    agg[k][0] += m["kept_apart"]
                    agg[k][1] += 1
            if "restored" in m:
                agg["restored"][0] += m["restored"]
                agg["restored"][1] += 1
        res[method] = dict(agg)
    return res


def pct(pair):
    a, b = pair if pair else (0, 0)
    return "–" if not b else f"{a / b:.0%}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=str(ROOT / "eval" / "data" / "test_set.jsonl"))
    ap.add_argument("--methods", nargs="+", default=["redact", "pseudonymize"], choices=list(LABEL))
    ap.add_argument("--threshold", type=float, default=0.4)
    ap.add_argument("--out", default=str(ROOT / "eval" / "results" / "methods_report.md"))
    args = ap.parse_args()
    rows = [json.loads(l) for l in open(args.data, encoding="utf-8")]
    M = args.methods

    results = {}
    for source in ("gold", "hybrid"):
        print(f"Running with {source} detections ...", flush=True)
        results[source] = summarise(rows, source, M, args.threshold)

    L = ["# Privacy comparison: full redaction vs pseudonymization\n",
         f"Synthetic test set: {len(rows)} prompts, {sum(len(r['entities']) for r in rows)} labelled items. "
         "\"Perfect detection\" uses the ground-truth labels; \"pipeline\" uses the hybrid detector.\n"]

    L += ["## Summary\n",
          "| Method | Detection | Residual leakage | Item types revealed | Number of people revealed | Same-person links revealed | People kept apart (2+ people) | Restored exactly |",
          "|---|---|---|---|---|---|---|---|"]
    for source, name in (("gold", "perfect"), ("hybrid", "pipeline")):
        for m in M:
            r = results[source][m]
            L.append(f"| {LABEL[m]} | {name} | {pct(r.get('leak'))} | {pct(r.get('type'))} | {pct(r.get('count'))} | "
                     f"{pct(r.get('links'))} | {pct(r.get('apart'))} | {pct(r.get('restored'))} |")

    cats = sorted({row["category"] for row in rows if row["category"] != "negative"})
    L += ["\n## Residual leakage by prompt type (pipeline detection)\n",
          "| Prompt type | " + " | ".join(LABEL[m] for m in M) + " |", "|---|" + "---|" * len(M)]
    for c in cats:
        L.append(f"| {c} | " + " | ".join(pct(results['hybrid'][m].get(f'leak_type:{c}')) for m in M) + " |")

    ents = sorted({g["type"] for row in rows for g in row["entities"]})
    L += ["\n## Residual leakage by entity type (pipeline detection)\n",
          "| Entity type | " + " | ".join(LABEL[m] for m in M) + " |", "|---|" + "---|" * len(M)]
    for e in ents:
        L.append(f"| {e} | " + " | ".join(pct(results['hybrid'][m].get(f'leak_ent:{e}')) for m in M) + " |")

    L += ["\n## People kept apart by prompt type (prompts with 2+ people)\n",
          "| Prompt type | " + " | ".join(f"{LABEL[m]} (perfect) | {LABEL[m]} (pipeline)" for m in M) + " |",
          "|---|" + "---|---|" * len(M)]
    for c in cats:
        L.append(f"| {c} | " + " | ".join(f"{pct(results['gold'][m].get(f'apart_type:{c}'))} | "
                                           f"{pct(results['hybrid'][m].get(f'apart_type:{c}'))}" for m in M) + " |")

    L.append("\nHow to read this: both methods share one detector, so residual leakage is the same for both; "
             "the privacy difference lies in what the format itself reveals. Full redaction hides item types, "
             "the number of distinct people and which mentions refer to the same person. Pseudonymization "
             "reveals all three, which is also what lets the AI tell people apart. With pipeline detection, "
             "a missed name reaches the AI as the real name: people can still be told apart, but that person "
             "is exposed (counted in residual leakage).\n")
    Path(args.out).write_text("\n".join(L), encoding="utf-8")
    (Path(args.out).with_suffix(".json")).write_text(json.dumps(results, indent=1), encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    main()
