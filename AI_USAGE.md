# AI_USAGE.md

## AI Tool Used
Claude (Anthropic), used as the primary development collaborator across the entire project — architecture design, code generation, live debugging, and documentation — under a strict "senior engineer explains, junior engineer implements" workflow: every file was reviewed, typed into the codebase, and run/verified locally before proceeding.

## Workflow
1. Discussed requirements and the actual CSV data in detail before any code was written.
2. Claude proposed database schema, API design, and algorithms with reasoning for each decision; I approved or redirected before implementation.
3. Every module was built incrementally: models → migrations → verified in Postgres/Django admin → service logic → tests → API → verified via real HTTP calls → committed.
4. All anomaly detectors were verified against the actual 42-row dataset, not synthetic examples.

## Key Prompts Used
- "Before implementing anything, briefly explain WHY the design is chosen."
- "Never generate code that you cannot explain or that I cannot reasonably understand."
- Iterative: "run this, paste the output" — used throughout to force verification against real data/behavior rather than trusting generated code by default.

## Concrete Cases Where AI Output Was Wrong (Caught and Corrected)

### 1. `simplify_debts` — silent infinite-loop-adjacent bug
The initial debt-simplification backtracking algorithm reassigned a debtor's balance to a creditor but never advanced the recursion index, and re-scanned from index 0 every call. Because the "already settled" value was never actually zeroed at the right point, the function silently returned an empty result instead of erroring. Caught by writing a verification script that asserted actual output (not just "did it run without crashing"), then fixed by passing an explicit index parameter through the recursion instead of re-scanning from the start each call. This was later formalized into a permanent regression test (`test_simplify_debts_settles_everyone_to_zero`) specifically because a bug that runs cleanly but returns wrong output is more dangerous in a financial app than one that crashes.

### 2. Description similarity using character-sequence comparison instead of word-set comparison
Claude's first implementation of duplicate-detection used Python's `difflib.SequenceMatcher` to compare expense descriptions. This scored "Dinner at Thalassa" vs "Thalassa dinner" at only ~48% similarity (below the detection threshold) because character-sequence matching is badly hurt by word reordering, even when the words themselves are identical. This was caught by manually testing the actual similarity score against the real duplicate pair in the dataset, not by inspecting the code. Fixed by switching to word-set (Jaccard) similarity, which ignores word order.

### 3. JSON serialization of datetime objects breaking date comparisons
The import pipeline's row-staging serializer converted Python `datetime` objects to ISO strings using `.isoformat()`, which produces `"2026-04-02T00:00:00"` (with a time component) rather than a bare date string. Django's `DateField` validator silently fails to parse that format during `full_clean()`, leaving the field as an un-converted string — which then caused a `TypeError` when `GroupMembership.is_active_on()` tried to compare it against a real `date` object. Caught via a live traceback during end-to-end testing, not anticipated in advance. Fixed by explicitly truncating `datetime` to `.date()` before calling `.isoformat()`, with an important subtlety: `isinstance(value, datetime)` must be checked before `isinstance(value, date)`, since `datetime` is a subclass of `date` in Python.

## Verification Discipline
Every service function (split calculation, balance calculation, anomaly detectors, import pipeline) was tested against the actual assignment data before being trusted, not just against hypothetical examples. Several of Claude's initial implementations passed on paper but failed against the real messy data — this is treated as an expected part of the process, not a failure: the real dataset was consistently the source of truth for whether logic actually worked, and multiple design decisions (see DECISIONS.md) were revised specifically because real data testing surfaced problems synthetic testing would have missed.