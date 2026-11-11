# Evaluation results

Synthetic test set: 400 prompts, 1738 labelled items. Threshold: 0.4.

## Overall by detection mode

| Mode | Precision | Recall | F1 | Leakage rate | False alarms on clean prompts | ms / prompt |
|---|---|---|---|---|---|---|
| rules | 1.00 | 0.63 | 0.77 | 36.9% | 0/70 prompts (0 items) | 6 |
| ner | 0.98 | 0.32 | 0.48 | 68.0% | 0/70 prompts (0 items) | 5 |
| hybrid | 0.99 | 0.95 | 0.97 | 5.2% | 0/70 prompts (0 items) | 6 |

## Recall by entity type

| Entity | rules | ner | hybrid |
|---|---|---|---|
| PERSON | 0.00 | 0.87 | 0.86 |
| EMAIL_ADDRESS | 1.00 | 0.00 | 1.00 |
| PHONE_NUMBER | 1.00 | 0.00 | 1.00 |
| CA_SIN | 1.00 | 0.00 | 1.00 |
| CREDIT_CARD | 1.00 | 0.00 | 1.00 |
| CA_POSTAL_CODE | 1.00 | 0.00 | 1.00 |
| STREET_ADDRESS | 1.00 | 0.00 | 1.00 |
| ACCOUNT_ID | 1.00 | 0.00 | 1.00 |

## Precision by entity type

| Entity | rules | ner | hybrid |
|---|---|---|---|
| PERSON | – | 0.98 | 0.98 |
| EMAIL_ADDRESS | 1.00 | – | 1.00 |
| PHONE_NUMBER | 1.00 | – | 1.00 |
| CA_SIN | 1.00 | – | 1.00 |
| CREDIT_CARD | 1.00 | – | 1.00 |
| CA_POSTAL_CODE | 1.00 | – | 1.00 |
| STREET_ADDRESS | 1.00 | – | 1.00 |
| ACCOUNT_ID | 1.00 | – | 1.00 |

## Recall and leakage by prompt type

| Prompt type | rules recall | rules leakage | ner recall | ner leakage | hybrid recall | hybrid leakage |
|---|---|---|---|---|---|---|
| advice | 0.59 | 40.6% | 0.38 | 61.9% | 0.97 | 2.6% |
| data | 0.70 | 30.3% | 0.23 | 76.9% | 0.93 | 7.4% |
| draft | 0.50 | 49.7% | 0.47 | 53.3% | 0.97 | 3.0% |
| summarize | 0.62 | 38.2% | 0.35 | 64.9% | 0.96 | 3.6% |

## Name recall by name origin (rules)

| Name origin | Recall | Names |
|---|---|---|
| Anglo-Canadian | 0.00 | 114 |
| Chinese (romanized) | 0.00 | 103 |
| French-Canadian | 0.00 | 92 |
| Hispanic | 0.00 | 123 |
| Nigerian | 0.00 | 124 |
| South Asian | 0.00 | 86 |

## Name recall by name origin (ner)

| Name origin | Recall | Names |
|---|---|---|
| Anglo-Canadian | 0.94 | 114 |
| Chinese (romanized) | 0.90 | 103 |
| French-Canadian | 0.87 | 92 |
| Hispanic | 0.89 | 123 |
| Nigerian | 0.82 | 124 |
| South Asian | 0.76 | 86 |

## Name recall by name origin (hybrid)

| Name origin | Recall | Names |
|---|---|---|
| Anglo-Canadian | 0.94 | 114 |
| Chinese (romanized) | 0.89 | 103 |
| French-Canadian | 0.87 | 92 |
| Hispanic | 0.89 | 123 |
| Nigerian | 0.81 | 124 |
| South Asian | 0.76 | 86 |

## Sample misses (hybrid)

- `PERSON` 'Charity Balogun' (prompt 13)
- `PERSON` 'Esmeralda Narváez' (prompt 29)
- `PERSON` 'Ucchal Sani' (prompt 31)
- `PERSON` 'Patience Adetokunbo' (prompt 32)
- `PERSON` 'Gabino Patiño' (prompt 32)
- `PERSON` 'Xiulan Song' (prompt 34)
- `PERSON` 'Vedhika Puri' (prompt 35)
- `PERSON` 'Elizabeth Ojo' (prompt 35)
- `PERSON` 'Jill Rivers' (prompt 40)
- `PERSON` 'Harita Thaker' (prompt 41)
- `PERSON` 'Gloria Olawale' (prompt 47)
- `PERSON` 'Raphaël Breton' (prompt 55)
- `PERSON` 'Morgan Fleming' (prompt 55)
- `PERSON` 'Li Tan' (prompt 59)
- `PERSON` 'Agnes Obi' (prompt 76)

## Sample false alarms (hybrid)

- `PERSON` 'Hamilton' (prompt 32)
- `PERSON` 'Hamilton' (prompt 45)
- `PERSON` 'Hamilton' (prompt 162)
- `PERSON` 'Hamilton' (prompt 194)
- `PERSON` 'Hamilton' (prompt 194)
- `PERSON` 'Hamilton' (prompt 213)
- `PERSON` 'Hamilton' (prompt 279)
- `PERSON` 'Hamilton' (prompt 312)
- `PERSON` 'Hamilton' (prompt 366)
- `PERSON` 'Hamilton' (prompt 399)
