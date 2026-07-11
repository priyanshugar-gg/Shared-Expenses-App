# DECISIONS.md

Format: Decision — Options considered — Why chosen

## Authentication: JWT (SimpleJWT) over sessions or plain tokens
Frontend and backend are deployed on separate domains (Vercel/Railway), making cross-origin cookie auth unnecessarily complex. JWT is stateless and standard for decoupled SPA+API architectures. Access tokens expire in 30 min (small blast radius if leaked); refresh tokens last 7 days.

## Database driver: psycopg3 over psycopg2
psycopg2 is in maintenance-only mode; psycopg3 has better wheel support for newer Python versions and active development.

## Money fields: DecimalField, never FloatField
Binary floating point cannot represent most decimal fractions exactly. A financial app with float arithmetic will silently drift over many transactions.

## Split rounding: largest-remainder method
Naive per-share rounding (e.g. ₹1000/3 = 333.33 × 3 = 999.99) loses money. Each share is floored to 2dp, then leftover paise are distributed one at a time to whichever share lost the most in rounding, guaranteeing splits always sum exactly to the original amount.

## Percentage splits that don't sum to 100%: never auto-normalize
The dataset has a real case (30+30+30+20=110%). Rescaling proportionally would silently change what someone agreed to pay, and there's no way to know which single value was the actual typo. Always routed to manual review.

## Currency conversion: fixed rate constant, not a live FX API or ExchangeRate table
No live rate source was provided or required by the assignment; only one currency pair (USD) appears. A settings constant (`USD_TO_INR_RATE`) is simple, auditable, and proportional to the actual requirement — a table would be premature structure for a single fixed value.

## Debt simplification: exact backtracking, not greedy heap heuristic
LeetCode-465-style backtracking finds the true minimum number of settling transactions. This is only tractable because group sizes are small (a handful of roommates) — a greedy approach would be the correct tradeoff at real scale (hundreds of users), but isn't needed here. Chose correctness over unneeded scalability.

## Import pipeline: two-phase scan → review → commit
Directly implements Meera's requirement ("I want to approve anything the app deletes or changes"). Nothing touches the real `Expense`/`Settlement` tables until an `ImportRow` is explicitly approved (or auto-approved under a narrow, documented rule: only when every anomaly on the row is cosmetic/low-severity). `raw_data` is written once and never modified; corrections live in a separate `resolved_data` field, so every auto-correction is a visible, auditable diff.

## Membership timeline: `GroupMembership.joined_at`/`left_at`, not derived from expense history
Directly solves the assignment's core scenario (Sam joining mid-April, Meera leaving end of March). Every expense split validates participants against `is_active_on(expense.date)` at creation time (manual API) and at import time (auto-exclusion + flagged recompute), rather than inferring membership from who happens to appear in expense data.

## Duplicate detection: word-set (Jaccard) similarity, not character-sequence similarity
Initial implementation used `difflib.SequenceMatcher` (character-level), which scored "Dinner at Thalassa" vs "Thalassa dinner" at only 48% similarity — reordered words tank character-sequence comparison even when the words are identical. Switched to word-set comparison (ignoring order and stopwords), which correctly scores this pair near 100%. Caught by testing against the actual dataset, not assumed correct from the standard library choice.

## No fuzzy name matching for ambiguous payers
"Priya S" doesn't exactly match "Priya" (or anyone else). A similarity-based matcher would likely auto-merge them, but "Priya S" could genuinely be a different person (e.g. a surname disambiguator). Consistent policy across the whole importer: genuine ambiguity is never silently resolved by the app.

## Split calculation service kept framework-agnostic (`split_service.py`)
No Django/DRF imports in the split math itself — pure functions taking Decimals and returning Decimals. This means the exact same calculation is reused identically by the manual expense-creation API and the CSV import commit phase, and is independently unit-testable without HTTP.

## Known simplification: import commit phase currently only handles equal splits
`commit_batch()` always calls `calculate_equal_split` for `create_expense` rows, regardless of the row's actual split_type. Full multi-split-type support in the commit path is the natural next increment — the detection and staging logic already captures split_type/split_details correctly; only the final calculation dispatch needs extending, following the same pattern already used in the manual expense API's serializer.