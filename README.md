# Prompt Redactor

CIS*6550 project prototype for *Redaction or Pseudonymization? A Privacy–Utility Evaluation of Prompt Sanitization for Generative AI*. A local web app that **warns** when a GenAI prompt contains personal information, lets the user **review** what was found, and then transforms it before the prompt is pasted into ChatGPT, Gemini or Copilot. The project compares two methods:

| Method | What the AI sees | Restorable? |
|---|---|---|
| **Full redaction** | Every item becomes the same token, `[REDACTED]` | No |
| **Pseudonymization** | Consistent typed placeholders: `[PERSON_1]`, `[EMAIL_1]`; the same value always gets the same placeholder | Yes, in the browser tab |

An optional extra condition, **surrogates**, replaces items with realistic fake values (e.g. "Sarah Thompson" becomes "Emily Clark"). It is not part of the main comparison.

Detection runs on the user's own machine (Python service on `127.0.0.1`). Unprotected text is never sent to any external service, and the app makes no outbound network calls.

## Setup (once)

Needs Python 3.10–3.13.

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m spacy download en_core_web_lg     # ~400 MB NER model, one-time download
```

## Run the app

```bash
python app.py
```

Open http://127.0.0.1:5000. Click **Load sample** to try it.

1. Paste a prompt and click **Check for personal information**.
2. Review the highlights. Click one to keep it as-is; select missed text to add it. Choose **Pseudonymize** or **Fully redact** (surrogates are under "Extra option").
3. Click **Create safer prompt**, then **Copy prompt**.
4. With pseudonymization (or surrogates), you can paste the AI's reply to swap the real details back in. This happens in the browser tab only.

## Surrogate values that can't be real (extra condition)

The surrogates look realistic but are chosen so they can never belong to a real person:

| Data | Fake value used |
|---|---|
| Email | Reserved domains `example.com`, `.org`, `.net` (RFC 2606). If the address was built from the person's name, the fake address is built from the fake name |
| Phone | 555-0100 to 555-0199, reserved for fiction in North America. The original format is kept |
| SIN | Starts with 0, which is never issued. Passes the checksum and keeps the format |
| Card number | Published test numbers of the same brand (Visa, Mastercard, Amex), which can't be charged |
| Postal code | Starts with Z or W, which Canada Post never uses as a first letter |
| Name, street, account ID | Random. Checked so they never match a real value in the same prompt and aren't everyday words ("Day", "Best"). Not guaranteed to be nobody's real name: this is a residual risk |

## Run the evaluation

```bash
python -m pytest -q                             # unit tests
python eval/generate.py --n 400 --seed 6550     # synthetic labelled test set
python eval/evaluate.py                         # DETECTION: rules vs NER vs hybrid
python eval/compare_methods.py                  # PRIVACY: what each method leaks and reveals
python eval/utility.py --n 60                   # UTILITY: AI answers, similarity + blind ratings (needs Ollama)
```

Results go to `eval/results/`.

### Utility test

This uses a local model through [Ollama](https://ollama.com). Original prompts are sent only because the dataset is synthetic.

```bash
ollama pull llama3.1:8b
pip install -r requirements-eval.txt            # sentence-transformers, bert-score
python eval/utility.py --n 60 --model llama3.1:8b
```

For each sampled prompt (an equal number per prompt type), the model answers the original, redacted and pseudonymized versions. The script then measures how similar each answer is to the answer to the original. Pseudonymized answers are scored after the real details are put back. Results are broken down by prompt type, by entity type, and by prompts with two or more people (`utility_report.md`). The script also writes a shuffled, blind `ratings.csv` for rubric ratings on a subset (`eval/RUBRIC.md`). After rating, run `python eval/utility.py --score`. Use `--similarity bertscore` for BERTScore, `--detections gold` to isolate the method from detection errors, and `--methods redact pseudonymize surrogate` to add the extra condition.

## User evaluation (study mode)

Added after the proposal feedback. Start the app with `python app.py --study` to show a study bar (participant ID, task, Start/Finish). It loads four synthetic tasks from `study/tasks.json`. Three of them contain a detail the detector misses on purpose (a lowercase name, a date of birth, a health detail). It assigns the method for T1/T2 by participant number (counterbalanced) and appends one row per task to `study_data/sessions.csv`.

The CSV holds **counts, timings and choices only**: items detected, unticked and added, method used, details still exposed, whether the planted detail was caught, and whether copy and restore were used. Prompt text is never stored.

Put questionnaire answers in `study_data/questionnaire.csv` (columns as in `study/questionnaire_template.csv`), then run `python study/analyze.py` to get `study_data/study_report.md`: task success, planted misses caught, ratings by method, preference, SUS and open answers. `study_data/` is excluded from Git. The protocol, consent text and questionnaires are in the separate User Evaluation Kit document.

## How it works

| File | What it does |
|---|---|
| `detector/recognizers.py` | Custom recognizers: SIN (with Luhn checksum), postal codes, street addresses, account/record IDs, Canadian phone formats, Mastercard 2-series |
| `detector/engine.py` | Builds the three detection modes and resolves overlaps (pattern matches beat NER) |
| `detector/transform.py` | Transformations: full redaction (`[REDACTED]`), pseudonymization (`[PERSON_1]`), optional surrogates; restore |
| `detector/offline.py` | Stops Presidio's `tldextract` dependency from downloading a list from the internet |
| `app.py` + `templates/` + `static/` | Local web interface: warn, review, choose a method, copy, restore |
| `eval/generate.py` | Synthetic prompts in four everyday task types (draft, summarize, advice, data) plus clean prompts with decoys, using fake data from Faker. Names come from six locales so name recall can be compared by origin |
| `eval/evaluate.py` | Detection: precision, recall and F1 per entity and prompt type; leakage; false alarms; name recall by origin |
| `eval/compare_methods.py` | Privacy: residual leakage by prompt and entity type; what each format reveals (types, number of people, same-person links); people kept apart; restore success. Perfect vs pipeline detection |
| `study/` | Study mode: tasks, recorder (counts only) and analysis script |
| `eval/utility.py` + `eval/RUBRIC.md` | Utility: answer similarity by prompt type, entity type and number of people; blind rubric ratings |

Entities in scope: names, emails, phone numbers, SINs, payment card numbers, postal codes, street addresses, and account/customer/patient/student IDs. Cities are **not** detected automatically (too many false alarms). Users can mark them by hand, and they are listed as a residual risk.

## Results so far (400 synthetic prompts, 1,738 labelled items)

**Detection** (threshold 0.4)

| Mode | Precision | Recall | F1 | Leakage | False alarms on clean prompts |
|---|---|---|---|---|---|
| Rules only | 1.00 | 0.63 | 0.77 | 36.9% | 0 / 70 |
| NER only | 0.98 | 0.32 | 0.48 | 68.0% | 0 / 70 |
| Hybrid | 0.99 | 0.95 | 0.97 | 5.2% | 0 / 70 |

Every remaining hybrid miss is a name (name recall 0.86). It varies by name origin: Anglo-Canadian 0.94, Chinese (romanized) 0.89, Hispanic 0.89, French-Canadian 0.87, Nigerian 0.81, South Asian 0.76.

**Privacy** (`eval/results/methods_report.md`)

| | Full redaction | Pseudonymization |
|---|---|---|
| Residual leakage (pipeline / perfect detection) | 5% / 0% | 5% / 0% |
| Reveals item types, number of people, same-person links | No | Yes |
| People kept apart (prompts with 2+ people) | 0% | 100% |
| Restorable | No | Yes |

Leakage is identical because both methods share one detector. The privacy difference lies in what each format reveals.

**Utility**: not run yet; it needs the model on the laptop (see above).

## Next steps

- Run the user evaluation (confirm ethics with Dr. Dara first).
- Run the utility test with Ollama, then rate the blind subset with two raters.
- Improve name recall (`en_core_web_trf`, context rules), then re-check fairness by origin.
- Threshold sweep: `evaluate.py --threshold` at 0.2–0.8.
- Heuristic usability walkthrough of the review screen (Phase 5).
