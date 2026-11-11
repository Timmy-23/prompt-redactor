"""Utility side of the comparison: how useful are a language model's answers
to the fully redacted and pseudonymized prompts, compared with its answer to
the original prompt? (proposal, Phase 4)

Each sampled prompt is sent three times: original, redacted, pseudonymized.
Original prompts are sent ONLY because the dataset is synthetic; in normal use
only transformed prompts leave the device. By default the model runs locally
through Ollama (https://ollama.com).

  1. Semantic similarity between the answer to the transformed prompt and the
     answer to the original prompt (sentence embeddings by default, BERTScore
     with --similarity bertscore). Pseudonymized answers are scored after the
     placeholders are swapped back ("restored"), as the user would see them;
     the raw score is reported too.
  2. Breakdown by prompt type, by entity type, and by prompts with 2+ people
     vs fewer (the proposal expects the gap to be largest when people must be
     told apart).
  3. A blind rating sheet for rubric ratings on a subset (eval/RUBRIC.md).

Setup on the laptop (once):
    ollama pull llama3.1:8b
    pip install -r requirements-eval.txt

Run:
    python eval/utility.py --n 60 --model llama3.1:8b
    python eval/utility.py --score        # after the rating sheet is filled in
"""
import argparse
import csv
import json
import random
import re
import statistics
import sys
import time
import urllib.request
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from detector import Detection, apply, detect, restore  # noqa: E402

OUT = ROOT / "eval" / "results" / "utility"
RATING_COLS = ["task_completed_0_2", "correct_and_useful_0_2", "details_kept_straight_0_2", "notes"]
LABEL = {"original": "Original", "redact": "Full redaction", "pseudonymize": "Pseudonymization",
         "surrogate": "Surrogates (extra)"}


# --- language model -----------------------------------------------------------
def ask_ollama(prompt: str, model: str, host: str, seed: int) -> str:
    body = json.dumps({"model": model, "prompt": prompt, "stream": False,
                       "options": {"temperature": 0, "seed": seed}}).encode()
    req = urllib.request.Request(f"{host}/api/generate", data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=600) as r:
        return json.loads(r.read())["response"].strip()


# --- similarity ---------------------------------------------------------------
class Similarity:
    """Semantic similarity between two answers, 0..1 (higher = more similar).

    sbert:     sentence-transformers all-MiniLM-L6-v2, cosine similarity (default)
    bertscore: BERTScore F1 (roberta-large; slower, as in Jathanna, 2026)
    spacy:     spaCy en_core_web_lg word vectors; a weak fallback only when
               neither library can be installed - say so in the report
    """

    def __init__(self, kind: str):
        self.kind = kind
        if kind == "sbert":
            from sentence_transformers import SentenceTransformer
            self.model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
        elif kind == "bertscore":
            import bert_score  # noqa: F401
        elif kind == "spacy":
            import spacy
            self.nlp = spacy.load("en_core_web_lg")
        else:
            raise ValueError(kind)

    def __call__(self, a: str, b: str) -> float:
        if not a.strip() or not b.strip():
            return 0.0
        if self.kind == "sbert":
            from sentence_transformers import util
            ea, eb = self.model.encode([a, b], convert_to_tensor=True)
            return float(util.cos_sim(ea, eb))
        if self.kind == "bertscore":
            from bert_score import score
            _, _, f1 = score([a], [b], lang="en", rescale_with_baseline=True, verbose=False)
            return float(f1[0])
        return float(self.nlp(a).similarity(self.nlp(b)))


def make_similarity(kind: str) -> Similarity:
    try:
        return Similarity(kind)
    except Exception as e:  # missing library or model download blocked
        if kind == "spacy":
            raise
        print(f"WARNING: could not load '{kind}' ({e.__class__.__name__}: {e}). "
              "Falling back to spaCy vectors; install requirements-eval.txt for the proper measure.", flush=True)
        return Similarity("spacy")


# --- run ----------------------------------------------------------------------
def generate(args):
    rows = [json.loads(l) for l in open(args.data, encoding="utf-8")]
    rng = random.Random(args.seed)
    pool = [r for r in rows if r["category"] != "negative"]
    # stratified sample: the same number of prompts from each prompt type
    by_cat = defaultdict(list)
    for r in pool:
        by_cat[r["category"]].append(r)
    per = max(1, args.n // len(by_cat))
    sample = [r for c in sorted(by_cat) for r in rng.sample(by_cat[c], min(per, len(by_cat[c])))]
    versions = ["original"] + args.methods
    sim = make_similarity(args.similarity)
    OUT.mkdir(parents=True, exist_ok=True)

    records = []
    for i, row in enumerate(sample, 1):
        text = row["text"]
        dets = (detect(text, mode="hybrid") if args.detections == "hybrid" else
                [Detection(g["type"], g["start"], g["end"], g["value"], 1.0, "gold") for g in row["entities"]])
        answers = {}
        for v in versions:
            if v == "original":
                sent, mapping = text, {}
            else:
                t = apply(text, dets, method=v, seed=row["id"])
                sent, mapping = t["text"], t["mapping"]
            t0 = time.time()
            resp = "(dry run) " + sent if args.dry_run else ask_ollama(sent, args.model, args.host, args.seed)
            restored = restore(resp, mapping)
            answers[v] = restored
            records.append({
                "prompt_id": row["id"], "prompt_type": row["category"], "n_people": row.get("n_people", 0),
                "entity_types": sorted({g["type"] for g in row["entities"]}),
                "version": v, "sent": sent, "response": resp, "restored": restored,
                "seconds": round(time.time() - t0, 1),
                "placeholders_left": len(re.findall(r"\[(?:REDACTED|[A-Z_]+_\d+)\]", restored)),
            })
        for rec in records[-len(versions):]:
            if rec["version"] != "original":
                rec["similarity_restored"] = round(sim(rec["restored"], answers["original"]), 4)
                rec["similarity_raw"] = round(sim(rec["response"], answers["original"]), 4)
        print(f"[{i}/{len(sample)}] prompt {row['id']} ({row['category']}) done", flush=True)

    with open(OUT / "responses.jsonl", "w", encoding="utf-8") as fh:
        for r in records:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    args.similarity = sim.kind  # record what was actually used (after any fallback)
    report(records, args, versions)
    rating_sheet(records, rng, args.rate_n)


def report(records, args, versions):
    methods = [v for v in versions if v != "original"]
    def mean(xs):
        xs = list(xs)
        return f"{statistics.mean(xs):.3f}" if xs else "–"
    def sims(pred, key="similarity_restored"):
        return {m: [r[key] for r in records if r["version"] == m and pred(r)] for m in methods}

    L = [f"# Utility comparison ({args.model}, {args.similarity} similarity, {args.detections} detections)\n",
         f"{len({r['prompt_id'] for r in records})} prompts. Similarity = how close the answer to the transformed "
         "prompt is to the answer to the original prompt (1.0 = same meaning).\n",
         "## Overall\n",
         "| Method | Similarity (restored) | Similarity (raw) | Answers still containing [REDACTED] or placeholders | Median seconds |",
         "|---|---|---|---|---|"]
    for m in methods:
        rs = [r for r in records if r["version"] == m]
        L.append(f"| {LABEL[m]} | {mean(r['similarity_restored'] for r in rs)} | {mean(r['similarity_raw'] for r in rs)} | "
                 f"{sum(r['placeholders_left'] > 0 for r in rs)}/{len(rs)} | {statistics.median(r['seconds'] for r in rs):.1f} |")

    L += ["\n## By prompt type (similarity, restored)\n",
          "| Prompt type | " + " | ".join(LABEL[m] for m in methods) + " | Gap |", "|---|" + "---|" * (len(methods) + 1)]
    for c in sorted({r["prompt_type"] for r in records}):
        s = sims(lambda r, c=c: r["prompt_type"] == c)
        gap = (statistics.mean(s["pseudonymize"]) - statistics.mean(s["redact"])
               if "pseudonymize" in s and "redact" in s and s["redact"] else None)
        L.append(f"| {c} | " + " | ".join(mean(s[m]) for m in methods) + f" | {'' if gap is None else f'{gap:+.3f}'} |")

    L += ["\n## By number of people in the prompt\n",
          "| People | " + " | ".join(LABEL[m] for m in methods) + " |", "|---|" + "---|" * len(methods)]
    for name, pred in (("0-1", lambda r: r["n_people"] < 2), ("2 or more", lambda r: r["n_people"] >= 2)):
        s = sims(pred)
        L.append(f"| {name} | " + " | ".join(mean(s[m]) for m in methods) + " |")

    L += ["\n## By entity type present in the prompt\n",
          "| Entity type | " + " | ".join(LABEL[m] for m in methods) + " |", "|---|" + "---|" * len(methods)]
    for e in sorted({e for r in records for e in r["entity_types"]}):
        s = sims(lambda r, e=e: e in r["entity_types"])
        L.append(f"| {e} | " + " | ".join(mean(s[m]) for m in methods) + " |")

    (OUT / "utility_report.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


def rating_sheet(records, rng, rate_n):
    """Blind sheet for rubric ratings on a subset (method hidden, rows shuffled)."""
    ids = sorted({r["prompt_id"] for r in records})
    subset = set(rng.sample(ids, min(rate_n, len(ids))))
    blind = [r for r in records if r["prompt_id"] in subset]
    rng.shuffle(blind)
    originals = {r["prompt_id"]: r["sent"] for r in records if r["version"] == "original"}
    with open(OUT / "ratings.csv", "w", newline="", encoding="utf-8") as fh, \
            open(OUT / "key.csv", "w", newline="", encoding="utf-8") as kh:
        w, k = csv.writer(fh), csv.writer(kh)
        w.writerow(["row", "prompt_id", "task_prompt", "answer_to_rate"] + RATING_COLS)
        k.writerow(["row", "prompt_id", "version"])
        for n, r in enumerate(blind, 1):
            w.writerow([n, r["prompt_id"], originals[r["prompt_id"]], r["restored"]] + [""] * len(RATING_COLS))
            k.writerow([n, r["prompt_id"], r["version"]])
    print(f"\nRate {OUT / 'ratings.csv'} ({len(blind)} answers) using eval/RUBRIC.md, "
          "then run: python eval/utility.py --score")


def score(_args):
    key = {row["row"]: row["version"] for row in csv.DictReader(open(OUT / "key.csv", encoding="utf-8"))}
    scores = defaultdict(lambda: defaultdict(list))
    for row in csv.DictReader(open(OUT / "ratings.csv", encoding="utf-8")):
        for col in RATING_COLS[:-1]:
            if row[col].strip():
                scores[key[row["row"]]][col].append(float(row[col]))
    L = ["# Rubric ratings (mean, 0-2)\n", "| Version | " + " | ".join(RATING_COLS[:-1]) + " | n |",
         "|---|" + "---|" * len(RATING_COLS)]
    for v in [v for v in LABEL if v in scores]:
        cols = scores[v]
        n = max((len(x) for x in cols.values()), default=0)
        L.append(f"| {LABEL[v]} | " + " | ".join(f"{statistics.mean(cols[c]):.2f}" if cols[c] else "–"
                                                  for c in RATING_COLS[:-1]) + f" | {n} |")
    (OUT / "ratings_summary.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=str(ROOT / "eval" / "data" / "test_set.jsonl"))
    ap.add_argument("--n", type=int, default=60, help="prompts to sample, split evenly across prompt types")
    ap.add_argument("--rate-n", type=int, default=20, help="prompts in the blind rubric-rating subset")
    ap.add_argument("--methods", nargs="+", default=["redact", "pseudonymize"],
                    choices=["redact", "pseudonymize", "surrogate"])
    ap.add_argument("--model", default="llama3.1:8b")
    ap.add_argument("--host", default="http://localhost:11434")
    ap.add_argument("--similarity", choices=["sbert", "bertscore", "spacy"], default="sbert")
    ap.add_argument("--seed", type=int, default=6550)
    ap.add_argument("--detections", choices=["hybrid", "gold"], default="hybrid",
                    help="hybrid = what users get; gold = perfect detection, isolates the method")
    ap.add_argument("--dry-run", action="store_true", help="test the pipeline without calling a model")
    ap.add_argument("--score", action="store_true", help="summarise the filled-in ratings.csv")
    args = ap.parse_args()
    score(args) if args.score else generate(args)


if __name__ == "__main__":
    main()
