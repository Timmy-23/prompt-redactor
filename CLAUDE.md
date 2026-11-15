# Project context for Claude Code

## What this is
CIS*6550 (Privacy, Compliance and Human Aspects of Cybersecurity), University of Guelph, Fall 2026. Instructor: Dr. Rozita Dara.
Team: Deborah Essien, Derick Akoto Brown, Olaleye Oluwatimilehin (Timmy). Timmy writes the report sections that describe the software.
Project (submitted proposal, Nov 5 2026): "Redaction or Pseudonymization? A Privacy–Utility Evaluation of Prompt Sanitization for Generative AI".
Deadline: final report, prototype and presentation Dec 10, 2026.

## Decisions (keep consistent with the submitted proposal)
- Local web app: Flask on 127.0.0.1 + Python detection. The proposal said Streamlit; the team kept Flask (the report explains the change). Text is processed on the user's machine; the app makes no outbound network calls (`detector/offline.py` exists for that reason).
- The app WARNS (highlights detections), lets the user REVIEW (keep/add items), then applies the chosen transformation (`detector/transform.py`):
  - `redact` = full redaction: every item becomes the uniform token [REDACTED]; not restorable.
  - `pseudonymize` = consistent typed placeholders [PERSON_1], [EMAIL_1] (category-unique, Deusser et al. 2026); mapping stays on the device; restorable. A one-word name that matches an earlier full name reuses its placeholder.
  - `surrogate` = OPTIONAL EXTRA, not in the main comparison: realistic fake values that can't be real (example.com emails, 555-01xx phones, SINs starting with 0, test card numbers, postal codes starting with Z/W).
- Detection: Microsoft Presidio analyzer + spaCy `en_core_web_lg` + custom recognizers (`detector/recognizers.py`). Modes: rules, ner, hybrid (default). Transformation is our own code, not presidio-anonymizer.
- In-scope entities: PERSON, EMAIL_ADDRESS, PHONE_NUMBER, CA_SIN, CREDIT_CARD, CA_POSTAL_CODE, STREET_ADDRESS, ACCOUNT_ID. Cities and free-text health details are out of scope (residual risks).
- Test data: synthetic prompts in four task types (draft, summarize, advice, data) + clean "negative" prompts. `n_people` is recorded per prompt.
- Detection metrics (`eval/evaluate.py`): P/R/F1 per entity and prompt type, leakage, false alarms, name recall by origin.
- Privacy metrics (`eval/compare_methods.py`): residual leakage by prompt/entity type; what each format reveals (item types, number of people, same-person links); people kept apart; restore. Perfect (gold) vs pipeline (hybrid) detection.
- Utility (`eval/utility.py`): local LLM via Ollama answers original / redacted / pseudonymized prompts; semantic similarity to the original answer (sentence-transformers default, BERTScore optional) by prompt type, entity type and 2+ people; blind rubric ratings on a subset (`eval/RUBRIC.md`).

- User evaluation (added after proposal feedback "add user evaluation and report their feedback"): `python app.py --study`; tasks in `study/tasks.json` (T0 practice, T1/T2 counterbalanced methods, T3 free choice; each of T1-T3 has one planted miss); `study/recorder.py` writes counts/timings only to `study_data/sessions.csv` (git-ignored); `study/analyze.py` summarises with the questionnaire CSV. Kit document: User_Evaluation_Kit.docx in the course folder.

## Rules
- Use SYNTHETIC data only. Never add real personal information to test data, fixtures, logs or commits.
- Don't add logging of prompt text, analytics or any external calls (including CDNs) to the app. Study mode must keep storing counts only.
- After changing detector or transform code, run `python -m pytest -q`, `python eval/evaluate.py` and `python eval/compare_methods.py`, and compare with the baseline below.

## Baseline (400 prompts, 1,738 items, seed 6550, threshold 0.4)
Detection: rules P 1.00 / R 0.63 / leakage 36.9%; ner P 0.98 / R 0.32 / 68.0%; hybrid P 0.99 / R 0.95 / 5.2%. 0/70 false alarms.
All hybrid misses are names (recall 0.86); by origin: Anglo-Canadian 0.94 ... South Asian 0.76.
Privacy: both methods leak 5% (pipeline) / 0% (perfect). Redaction reveals no types/people/links and keeps 0% of people apart; pseudonymization reveals all three and keeps 100% apart; only pseudonymization is restorable.
Utility: not run yet.

## Next steps
0. Run the user study (6-10 participants) once Dr. Dara confirms ethics.
1. Run `eval/utility.py --n 60 --model llama3.1:8b` on the laptop; rate the blind subset with two raters; `--score`.
2. Improve name recall (en_core_web_trf, context rules), re-check fairness by origin.
3. Threshold sweep (0.2–0.8).
4. Heuristic usability walkthrough of the review screen.

## Commands
- Setup: `python -m venv .venv`, activate, `pip install -r requirements.txt`, `python -m spacy download en_core_web_lg`; for utility also `pip install -r requirements-eval.txt`
- App: `python app.py` → http://127.0.0.1:5000
- Tests: `python -m pytest -q`
- Eval: `python eval/generate.py --n 400`, `python eval/evaluate.py`, `python eval/compare_methods.py`, `python eval/utility.py --n 60`
