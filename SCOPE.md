# SCOPE.md

## Anomaly Log

The provided file (`expenses_export_assigbment_annex.xlsx` — note: assignment refers to it as `.csv`, but the actual provided file is `.xlsx`; the importer was built against the real file format) contains 42 data rows. The importer detects the following 15 anomaly categories, listed with their exact source rows, detection logic, and handling policy.

| # | Anomaly Type | Row(s) | Detection | Policy |
|---|---|---|---|---|
| 1 | Exact duplicate | 6 (dup of 5) | Same date/payer/amount + ≥85% word-set description similarity | Skip second occurrence, requires approval |
| 2 | Suspected duplicate | 24, 25 (Thalassa) | Same date, similar description, different amount/payer | Flag both, needs manual review — never auto-merge |
| 3 | Payer name casing/whitespace | 9 (`priya`), 27 (`rohan `) | Case/whitespace-insensitive match to real member | Auto-normalize, low severity, shown in report |
| 4 | Ambiguous payer identity | 11 (`Priya S`) | No exact match to any member | Flag, needs manual review — no fuzzy matching |
| 5 | Missing payer | 13 | Empty field | Flag, needs manual review |
| 6 | Settlement misclassified as expense | 14 | Single-recipient split_with + explicit "paid...back" language | Auto-reclassify to Settlement |
| 7 | Possible settlement (low confidence) | 38 (Sam's deposit) | Single-recipient split_with, no explicit repayment language | Flag, needs manual review (not auto-reclassified) |
| 8 | Percentage split ≠ 100% | 15, 32 (sum to 110%) | Sum of split_details percentages | Flag, needs manual review — never auto-normalize |
| 9 | Multi-currency (USD) | 18-21, 23, 26 (Goa trip) | currency field | Store original + fixed-rate INR conversion, both preserved |
| 10 | Non-member participant | 23 ("Dev's friend Kabir") | split_with name doesn't resolve to a member | Flag, needs manual review |
| 11 | Negative amount | 26 (refund) | amount < 0 | "refund" keyword → auto-approve as reversal (low); else flag high |
| 12 | Implausible date | 27 (year 2014) | Outside dataset's trimmed date range ± buffer | Flag, needs manual review |
| 13 | Ambiguous date format | 34 (source notes flag it) | Notes contain "?" + a month name | Flag, needs manual review — date not auto-parsed |
| 14 | Missing currency | 28 | Empty field | Default to INR, flagged (medium severity) |
| 15 | Zero amount | 31 | amount == 0 | Auto-approve, flagged (no financial effect) |
| 16 | Inactive member in split | 27 (secondary), 36 (Meera post-departure) | GroupMembership.is_active_on(date) | Auto-exclude inactive member, recompute split, flagged HIGH severity, requires approval |
| 17 | split_type/split_details contradiction | 42 | split_type=equal but split_details present | Flag, low severity (no numeric effect) |
| 18 | Excess decimal precision | 10 (899.995) | >2 decimal places | Round to nearest paisa, flagged |

**Auto-approval rule:** a row auto-approves only if every anomaly on it is `severity: low` (purely cosmetic, zero effect on any amount). Anything medium/high always requires explicit human approval — this is the direct implementation of "never silently modify data."

## Database Schema
User (Django built-in)               - login credential only
Group                                 - a household
id, name, created_by, created_at
GroupMembership                       - time-bounded membership (THE key table)
id, group, user, joined_at, left_at (null = still active)
.is_active_on(date) -> bool
Expense
id, group, description, paid_by (FK GroupMembership, PROTECT),
date, currency, amount, exchange_rate_used, amount_base_currency,
split_type, notes, source (manual/import), created_at
ExpenseSplit                          - one row per participant per expense
id, expense, member (FK GroupMembership, PROTECT), share_amount
Settlement                            - direct payment, not split
id, group, paid_by, paid_to, amount, currency, date, source
ImportBatch                           - one CSV upload
id, group, file_name, uploaded_by, status, total_rows
ImportRow                             - one staged CSV row
id, batch, row_number, raw_data (JSON, never modified),
resolved_data (JSON, auto-corrections only),
anomalies (JSON list), proposed_action, resolution,
resulting_expense (FK, SET_NULL), resulting_settlement (FK, SET_NULL)

**Why `GroupMembership` is separate from `User`:** a group member is a financial participant; a `User` is a login credential. This lets historical CSV data reference people (or ambiguous names) without requiring every name to be a real account.

**Why `Expense`/`ExpenseSplit` FKs to `GroupMembership` use `PROTECT`:** prevents accidental deletion of financial history as a side effect of an unrelated membership change.

**Why `ImportRow` → `Expense`/`Settlement` FKs use `SET_NULL`:** the relationship points the informational direction (import record → what it created); a later legitimate expense deletion shouldn't be blocked by an old import audit record.