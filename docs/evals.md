# Evals and spend

Every number here comes from a committed run (`docs/evals/*.json`). All data is fictional. Rebuilt by the eval scripts; don't edit by hand.

## Call gym

Not run yet.

## Adversarial plan reviewer

| Scenario | Rounds | Final verdict | Revisions | Cost |
|---|---|---|---|---|
| full | 1 | 1 reasons stand | 0 | $0.094 |
| thin | 1 | 3 reasons stand | 0 | $0.091 |
| strong-standard | 2 | no reason to deny | 1 | $0.103 |

Reviewer: Muse Spark Open. Command: `python scripts/stress_test_appeal.py [--thin | --strong --standard]`.

## Cross-family judges

Not run yet.

## Reader eval

33 fictional documents x 4 messiness levels = 132 reads by `muse-spark-1.3` on 2026-10-29. Overall field accuracy **97.4%**.

| Messiness | Fields right | Accuracy |
|---|---|---|
| clean | 274/275 | 99.6% |
| phone | 274/275 | 99.6% |
| messy | 273/275 | 99.3% |
| harsh | 250/275 | 90.9% |

| Field | Right | Accuracy |
|---|---|---|
| bill.account | 39/44 | 89% |
| bill.amount_due | 43/44 | 98% |
| bill.biller | 44/44 | 100% |
| bill.lines | 41/44 | 93% |
| bill.patient_name | 43/44 | 98% |
| bill.service_date | 44/44 | 100% |
| denial_letter.appeal_by | 44/44 | 100% |
| denial_letter.appeal_days | 44/44 | 100% |
| denial_letter.appeals_fax | 44/44 | 100% |
| denial_letter.case_number | 42/44 | 95% |
| denial_letter.criteria | 44/44 | 100% |
| denial_letter.denied_on | 44/44 | 100% |
| denial_letter.expedited_available | 44/44 | 100% |
| denial_letter.member_id | 41/44 | 93% |
| denial_letter.member_name | 44/44 | 100% |
| denial_letter.plan | 44/44 | 100% |
| denial_letter.reason_category | 40/44 | 91% |
| denial_letter.reason_quote | 44/44 | 100% |
| denial_letter.service | 44/44 | 100% |
| eob.claim | 40/44 | 91% |
| eob.lines | 39/44 | 89% |
| eob.member_name | 44/44 | 100% |
| eob.payer | 44/44 | 100% |
| eob.service_date | 44/44 | 100% |
| eob.total_you_owe | 43/44 | 98% |

## Voice loop

Not run yet.

## Spend log

Prices in `src/eval/spend.py` (USD per 1M tokens). Rule: stop and ask before any single run projected over $25, or once either partner credit is 70% used.

| Provider | Spent | Credit | Used |
|---|---|---|---|
| meta | $18.98 | $150 | 12.7% |
| fireworks | $4.96 | $100 | 5.0% |
| baseten | $0.00 | $100 | 0.0% |

| When | Run | Detail | Meta | Fireworks | Baseten |
|---|---|---|---|---|---|
| 2026-10-29 04:12 | smoke | 1 chat + 1 JSON request on each partner (Baseten returned 403) | $0.000 | $0.001 | $0.000 |
| 2026-10-29 04:12 | reviewer live | 8 stress-test runs (full appeal on Meta + reviewer on Fireworks) | $0.687 | $0.051 | $0.000 |
| 2026-10-29 04:12 | gym pilot | 10 calls, seed 7 | $0.239 | $0.069 | $0.000 |
| 2026-10-29 04:15 | reader eval | 132 vision reads | $0.606 | $0.000 | $0.000 |
| 2026-10-29 04:15 | reader eval (lost) | estimate: 33 harsh-level reads; a piped command killed the script before it saved (33 x $0.0046) | $0.152 | $0.000 | $0.000 |
| 2026-10-29 04:16 | call gym | 600 calls, seed 7 (first headline run: 3 safety failures) | $14.223 | $3.983 | $0.000 |
| 2026-10-29 04:20 | call gym check | 112 calls, seed 7, kinds spanish_first,ai_refuser,mishears | $2.706 | $0.834 | $0.000 |
| 2026-10-29 04:21 | reviewer live | stress test, scenario thin | $0.086 | $0.005 | $0.000 |
| 2026-10-29 04:21 | reviewer live | stress test, scenario strong-standard | $0.096 | $0.007 | $0.000 |
| 2026-10-29 04:21 | reviewer live | stress test, scenario full | $0.093 | $0.007 | $0.000 |
| 2026-10-29 04:23 | reviewer live | stress test, scenario full | $0.089 | $0.004 | $0.000 |
