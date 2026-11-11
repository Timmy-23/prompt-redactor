# Privacy comparison: full redaction vs pseudonymization

Synthetic test set: 400 prompts, 1738 labelled items. "Perfect detection" uses the ground-truth labels; "pipeline" uses the hybrid detector.

## Summary

| Method | Detection | Residual leakage | Item types revealed | Number of people revealed | Same-person links revealed | People kept apart (2+ people) | Restored exactly |
|---|---|---|---|---|---|---|---|
| Full redaction | perfect | 0% | 0% | 0% | 0% | 0% | 0% |
| Pseudonymization | perfect | 0% | 100% | 100% | 100% | 100% | 100% |
| Full redaction | pipeline | 5% | 0% | 0% | 0% | 0% | 0% |
| Pseudonymization | pipeline | 5% | 100% | 100% | 100% | 100% | 100% |

## Residual leakage by prompt type (pipeline detection)

| Prompt type | Full redaction | Pseudonymization |
|---|---|---|
| advice | 3% | 3% |
| data | 7% | 7% |
| draft | 3% | 3% |
| summarize | 4% | 4% |

## Residual leakage by entity type (pipeline detection)

| Entity type | Full redaction | Pseudonymization |
|---|---|---|
| ACCOUNT_ID | 0% | 0% |
| CA_POSTAL_CODE | 0% | 0% |
| CA_SIN | 0% | 0% |
| CREDIT_CARD | 0% | 0% |
| EMAIL_ADDRESS | 0% | 0% |
| PERSON | 14% | 14% |
| PHONE_NUMBER | 0% | 0% |
| STREET_ADDRESS | 0% | 0% |

## People kept apart by prompt type (prompts with 2+ people)

| Prompt type | Full redaction (perfect) | Full redaction (pipeline) | Pseudonymization (perfect) | Pseudonymization (pipeline) |
|---|---|---|---|---|
| advice | 0% | 0% | 100% | 100% |
| data | 0% | 0% | 100% | 100% |
| draft | 0% | 0% | 100% | 100% |
| summarize | 0% | 0% | 100% | 100% |

How to read this: both methods share one detector, so residual leakage is the same for both; the privacy difference lies in what the format itself reveals. Full redaction hides item types, the number of distinct people and which mentions refer to the same person. Pseudonymization reveals all three, which is also what lets the AI tell people apart. With pipeline detection, a missed name reaches the AI as the real name: people can still be told apart, but that person is exposed (counted in residual leakage).
