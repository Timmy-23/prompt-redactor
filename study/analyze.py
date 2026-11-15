"""Summarize the user evaluation.

Inputs
  study_data/sessions.csv          written by the app in study mode (one row per task)
  study_data/questionnaire.csv     questionnaire answers, same columns as
                                   study/questionnaire_template.csv (e.g. a Google
                                   Forms export with the headers renamed)

Output
  study_data/study_report.md       tables for the report, plus all open answers

    python study/analyze.py
"""
import csv
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "study_data"
TASKS = ["T1", "T2", "T3"]  # T0 is practice and is left out
LABEL = {"pseudonymize": "Pseudonymization", "redact": "Full redaction", "surrogate": "Surrogates", "none": "None"}


def read(path):
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as fh:
        return [r for r in csv.DictReader(fh) if not r.get("participant", "").startswith("P00")]


def num(xs):
    return [float(x) for x in xs if str(x).strip() not in ("", "None")]


def mean_sd(xs):
    xs = num(xs)
    if not xs:
        return "–"
    return f"{statistics.mean(xs):.2f}" + (f" (SD {statistics.stdev(xs):.2f})" if len(xs) > 1 else "")


def pct(a, b):
    return "–" if not b else f"{a}/{b} ({a / b:.0%})"


def sus_score(r):
    """Standard SUS: odd items score-1, even items 5-score, sum x 2.5 (0-100)."""
    try:
        v = [int(r[f"sus{i}"]) for i in range(1, 11)]
    except (KeyError, ValueError):
        return None
    return 2.5 * sum((x - 1) if i % 2 == 0 else (5 - x) for i, x in enumerate(v))


def sus_adjective(s):
    # Bangor, Kortum & Miller (2009) adjective ratings, approximate cut-offs
    return ("Excellent" if s >= 85 else "Good" if s >= 72 else "OK" if s >= 52 else "Poor" if s >= 38 else "Awful")


def main():
    sessions = [r for r in read(DATA / "sessions.csv") if r["task"] in TASKS]
    quest = read(DATA / "questionnaire.csv")
    if not sessions and not quest:
        sys.exit("No data yet: run the app with --study, and put questionnaire answers in study_data/questionnaire.csv")

    # keep the last record per participant and task (in case a task was redone)
    last = {}
    for r in sessions:
        last[(r["participant"], r["task"])] = r
    sessions = list(last.values())
    participants = sorted({r["participant"] for r in sessions} | {q["participant"] for q in quest})

    L = ["# User evaluation results\n", f"Participants: {len(participants)}. Tasks T1–T3 (T0 was practice).\n"]

    # --- task performance ----------------------------------------------------
    L += ["## Task performance (from study mode)\n",
          "| Task | Completed with nothing exposed | Planted miss caught by participant | Median time (s) | Median review time (s) | Items added (mean) | Items unticked (mean) |",
          "|---|---|---|---|---|---|---|"]
    for t in TASKS:
        rs = [r for r in sessions if r["task"] == t]
        if not rs:
            continue
        L.append(f"| {t} | {pct(sum(r['n_exposed'] == '0' for r in rs), len(rs))} | "
                 f"{pct(sum(r['planted_protected'] == '1' for r in rs), len(rs))} | "
                 f"{statistics.median(num(r['seconds_total'] for r in rs)):.0f} | "
                 f"{statistics.median(num(r['seconds_review'] for r in rs)):.0f} | "
                 f"{statistics.mean(num(r['n_added'] for r in rs)):.1f} | {statistics.mean(num(r['n_unticked'] for r in rs)):.1f} |")

    exposed_types = Counter(t for r in sessions for t in r["exposed_types"].split(";") if t)
    if exposed_types:
        L.append("\nTypes of details still exposed when a task was finished: "
                 + ", ".join(f"{k} ({v})" for k, v in exposed_types.most_common()) + ".")

    # --- by method (T1 and T2 are counterbalanced) -------------------------------
    by_method = defaultdict(list)
    for r in sessions:
        if r["task"] in ("T1", "T2"):
            by_method[r["method_used"]].append(r)
    qa = {q["participant"]: q for q in quest}
    L += ["\n## Methods compared (T1 and T2, counterbalanced)\n",
          "| Method | Tasks | Nothing exposed | Answer useful (1–5) | Confident nothing leaked (1–5) | Easy (1–5) |",
          "|---|---|---|---|---|---|"]
    for m in ("pseudonymize", "redact"):
        rs = by_method.get(m, [])
        rating = lambda key: [qa[r["participant"]].get(f"{r['task'].lower()}_{key}", "") for r in rs if r["participant"] in qa]
        L.append(f"| {LABEL[m]} | {len(rs)} | {pct(sum(r['n_exposed'] == '0' for r in rs), len(rs))} | "
                 f"{mean_sd(rating('useful'))} | {mean_sd(rating('confident'))} | {mean_sd(rating('easy'))} |")

    # --- preference -------------------------------------------------------------
    chosen = Counter(r["method_used"] for r in sessions if r["task"] == "T3")
    stated = Counter(q.get("preference", "").strip() for q in quest if q.get("preference", "").strip())
    L += ["\n## Preference\n",
          "Method chosen freely in T3: " + (", ".join(f"{LABEL.get(k, k)} {v}" for k, v in chosen.most_common()) or "–") + ".  ",
          "Stated preference after the session: " + (", ".join(f"{LABEL.get(k, k)} {v}" for k, v in stated.most_common()) or "–") + ".  ",
          f"Would use a tool like this before pasting into an AI (1–5): {mean_sd(q.get('would_use', '') for q in quest)}."]

    # --- SUS ------------------------------------------------------------------
    sus = [s for s in (sus_score(q) for q in quest) if s is not None]
    if sus:
        m = statistics.mean(sus)
        L += ["\n## System Usability Scale\n",
              f"Mean SUS {m:.1f} (SD {statistics.stdev(sus):.1f}, n = {len(sus)}), range {min(sus):.0f}–{max(sus):.0f}. "
              f"Adjective rating: {sus_adjective(m)} (Bangor et al., 2009). The commonly used average benchmark is 68."]

    # --- participants -----------------------------------------------------------
    if quest:
        L += ["\n## Participants\n",
              "GenAI use: " + ", ".join(f"{k} {v}" for k, v in Counter(q.get("genai_use", "") for q in quest).most_common()) + ".  ",
              "Background: " + ", ".join(f"{k} {v}" for k, v in Counter(q.get("background", "") for q in quest).most_common()) + "."]

    # --- open answers -------------------------------------------------------------
    for col, title in (("why_preference", "Why they preferred a method"),
                       ("noticed_missed", "Did they notice anything the tool missed?"),
                       ("trust_improve", "What would make them trust or use the tool")):
        answers = [(q["participant"], q.get(col, "").strip()) for q in quest if q.get(col, "").strip()]
        if answers:
            L.append(f"\n## {title}\n")
            L += [f"- **{p}:** {a}" for p, a in answers]

    out = DATA / "study_report.md"
    out.write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))
    print(f"\nSaved to {out}")


if __name__ == "__main__":
    main()
