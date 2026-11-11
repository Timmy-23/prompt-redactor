# Usefulness rubric

Used with `eval/results/utility/ratings.csv`. Each row shows the original task and one AI answer. The answer has already had real details put back where possible. You do not know whether it came from the original, the fully redacted or the pseudonymized prompt. Don't open `key.csv` until all rows are rated.

Ideally two team members rate every row independently. Then compare scores and discuss any row where you differ by 2.

| Score | task_completed | correct_and_useful | details_kept_straight |
|---|---|---|---|
| **2** | Does everything the prompt asked (e.g. sorts all records, writes the full email) | Accurate, and you would use it as-is or with tiny edits | Every person, number and address is attached to the right record or person |
| **1** | Does part of the task, or adds unnecessary caveats before doing it | Mostly right but needs noticeable fixing | One or two details are mixed up, missing or replaced by a label like [NAME] |
| **0** | Refuses, only comments on the redaction, or does a different task | Wrong or not usable | Details are mixed up or missing so the answer can't be used |

In `notes`, record anything worth discussing in the report. Examples:
- the model complained about missing information
- the model "corrected" a fake value (e.g. said a SIN or postal code looks invalid)
- a fake value was changed by the model, so restoring failed
- a placeholder like [NAME] appears in the final answer
