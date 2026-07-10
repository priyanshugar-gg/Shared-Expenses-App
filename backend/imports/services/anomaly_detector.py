"""
Anomaly detection for the CSV import pipeline.

Each detect_* function inspects one row (plus whatever context it
needs - e.g. the group's actual members, or other rows for duplicate
checking) and returns a list of anomaly dicts:
    {"type": "...", "message": "...", "severity": "low"|"medium"|"high"}

Detectors never mutate the row - they only report findings. The
import_service orchestrator decides what to do with those findings
(set proposed_action, write resolved_data, etc.) - keeping detection
and decision-making as separate concerns, same pattern as
split_service.py being pure calculation with no DB writes.
"""


def resolve_member(raw_name, group_members):
    """
    Attempts to match a raw payer/participant name from the CSV to an
    actual group member, using ONLY exact matching after trimming
    whitespace and normalizing case. Deliberately does NOT do fuzzy/
    similarity matching - see DECISIONS.md for why: a close-but-wrong
    auto-match on a person's identity is a much worse failure mode
    than asking a human to resolve it, since it would silently
    misattribute real money to the wrong person.

    group_members: list of GroupMembership objects (or objects with
    a `.user.username` attribute)
    raw_name: string from the CSV, e.g. "priya", " Rohan ", "Priya S"

    Returns the matching GroupMembership, or None if no exact
    (case/whitespace-insensitive) match exists.
    """
    if not raw_name:
        return None

    normalized_input = raw_name.strip().lower()

    for membership in group_members:
        if membership.user.username.strip().lower() == normalized_input:
            return membership

    return None


def needs_normalization(raw_name, matched_membership):
    """
    True if raw_name matched a member only after trimming/case-folding
    (e.g. "priya" -> Priya, "rohan " -> Rohan) - i.e. it wasn't an
    exact literal match. Used to flag auto-corrections in the report,
    even though they don't block the row from proceeding.
    """
    if matched_membership is None:
        return False
    return raw_name != matched_membership.user.username


def detect_missing_payer(row_data):
    """Anomaly: paid_by field is empty/null. Row cannot proceed without
    a resolved payer - this is a required field for a real Expense."""
    if not row_data.get("paid_by"):
        return [{
            "type": "missing_payer",
            "message": "Payer field is empty - cannot determine who paid this expense.",
            "severity": "high",
        }]
    return []


def detect_ambiguous_payer(row_data, group_members):
    """
    Anomaly: payer name doesn't match any group member, even after
    trimming/case-folding. Covers both genuine typos/unknown people
    (e.g. "Priya S") and would also catch a payer name that's simply
    misspelled beyond whitespace/casing differences.
    """
    raw_name = row_data.get("paid_by")
    if not raw_name:
        return []  # handled by detect_missing_payer instead

    matched = resolve_member(raw_name, group_members)
    if matched is None:
        return [{
            "type": "ambiguous_payer",
            "message": (
                f"Payer '{raw_name}' does not match any group member. "
                f"Could be a typo, a different person, or someone not yet added to the group."
            ),
            "severity": "high",
        }]
    return []


def detect_payer_name_normalization(row_data, group_members):
    """
    Not an error - a low-severity, informational flag that the payer
    name was auto-corrected (casing/whitespace) to match a real member.
    Still surfaced in the report per "never silently modify data" -
    even a harmless auto-correction must be visible, just not blocking.
    """
    raw_name = row_data.get("paid_by")
    if not raw_name:
        return []

    matched = resolve_member(raw_name, group_members)
    if matched and needs_normalization(raw_name, matched):
        return [{
            "type": "payer_name_normalized",
            "message": f"Payer '{raw_name}' auto-corrected to '{matched.user.username}' (casing/whitespace only).",
            "severity": "low",
        }]
    return []

import difflib


def _normalize_description(description):
    """
    Lowercases, strips, and collapses whitespace/punctuation so
    "Dinner at Marina Bites" and "dinner - marina bites" compare
    as equivalent. Deliberately simple (no stemming/NLP) - this is
    for catching obvious formatting-only differences, not doing
    semantic matching.
    """
    if not description:
        return ""
    normalized = description.lower().strip()
    for char in ["-", "_", ",", "."]:
        normalized = normalized.replace(char, " ")
    return " ".join(normalized.split())
STOPWORDS = {"at", "the", "a", "an", "for", "in", "on", "of"}


def _description_similarity(description_a, description_b):
    """
    Word-set (Jaccard) similarity: the proportion of words shared
    between two descriptions, ignoring order and common filler words
    ("at", "the", ...). Chosen over character-sequence similarity
    (difflib.SequenceMatcher) specifically because expense
    descriptions commonly get reworded/reordered by different people
    logging the same event - e.g. "Dinner at Thalassa" vs "Thalassa
    dinner" - which character-sequence comparison scores as very
    dissimilar (~0.48) despite being obviously the same words,
    just reordered. Word-set comparison correctly scores this as a
    near-perfect match instead.
    """
    words_a = set(_normalize_description(description_a).split()) - STOPWORDS
    words_b = set(_normalize_description(description_b).split()) - STOPWORDS

    if not words_a or not words_b:
        return 0.0

    intersection = words_a & words_b
    union = words_a | words_b
    return len(intersection) / len(union)

def _row_signature(row_data):
    """
    (date, normalized payer, amount, normalized description) - used
    as the exact-duplicate key. Payer is normalized the same way as
    detect_payer_name_normalization, so "Dev" and "dev" collapse to
    the same signature.
    """
    payer = (row_data.get("paid_by") or "").strip().lower()
    description = _normalize_description(row_data.get("description"))
    amount = row_data.get("amount")
    date = row_data.get("date")
    return (date, payer, amount, description)


def detect_exact_duplicates(all_rows, similarity_threshold=0.85):
    """
    Same date, same normalized payer, same amount, and a HIGHLY similar
    description (>= similarity_threshold) - treated as the same expense
    logged twice with only cosmetic wording differences (casing,
    punctuation, minor word choice like "at" vs a dash). The first
    occurrence proceeds; later ones are flagged and default to skip.

    Deliberately stricter on amount/payer (must match exactly) than on
    description (allowed to vary) - a duplicate entry of the same
    expense would never have a different amount or payer, only
    different formatting of the same description.
    """
    results = {}
    rows_list = sorted(all_rows, key=lambda r: r["row_number"])
    kept_rows = []  # rows confirmed NOT duplicates of anything earlier

    for row in rows_list:
        data = row["data"]
        payer = (data.get("paid_by") or "").strip().lower()
        amount = data.get("amount")
        date = data.get("date")
        description = _normalize_description(data.get("description"))

        found_duplicate_of = None
        for kept in kept_rows:
            kept_data = kept["data"]
            kept_payer = (kept_data.get("paid_by") or "").strip().lower()
            if kept_data.get("date") != date or kept_payer != payer or kept_data.get("amount") != amount:
                continue
            similarity = _description_similarity(data.get("description"), kept_data.get("description"))
            if similarity >= similarity_threshold:
                found_duplicate_of = kept["row_number"]
                break

        if found_duplicate_of:
            results[row["row_number"]] = [{
                "type": "exact_duplicate",
                "message": (
                    f"Same date, payer, and amount as row {found_duplicate_of}, with only "
                    f"cosmetic wording differences in the description - likely the same "
                    f"expense logged twice."
                ),
                "severity": "medium",
            }]
        else:
            kept_rows.append(row)

    return results


def detect_suspected_duplicates(all_rows, similarity_threshold=0.7):
    """
    Same date + similar (not necessarily identical) description, but a
    DIFFERENT amount or payer - can't be auto-resolved (which one is
    correct?), so both rows are flagged for manual review. Rows already
    caught by detect_exact_duplicates are skipped here to avoid
    double-flagging the same pair under two different anomaly types.
    """
    results = {}
    rows_list = sorted(all_rows, key=lambda r: r["row_number"])
    exact_duplicate_rows = set(detect_exact_duplicates(all_rows).keys())

    for i, row_a in enumerate(rows_list):
        if row_a["row_number"] in exact_duplicate_rows:
            continue
        for row_b in rows_list[i + 1:]:
            if row_b["row_number"] in exact_duplicate_rows:
                continue

            data_a, data_b = row_a["data"], row_b["data"]
            if data_a.get("date") != data_b.get("date"):
                continue

            similarity = _description_similarity(data_a.get("description"), data_b.get("description"))

            amount_differs = data_a.get("amount") != data_b.get("amount")
            payer_differs = (data_a.get("paid_by") or "").strip().lower() != (data_b.get("paid_by") or "").strip().lower()

            if similarity >= similarity_threshold and (amount_differs or payer_differs):
                message = (
                    f"Similar description to row {{other}} on the same date "
                    f"({similarity:.0%} similar) but "
                    f"{'amount' if amount_differs else ''}"
                    f"{' and ' if amount_differs and payer_differs else ''}"
                    f"{'payer' if payer_differs else ''} differ - possibly the same "
                    f"event logged twice with conflicting details."
                )
                anomaly_a = {"type": "suspected_duplicate", "message": message.format(other=row_b["row_number"]), "severity": "medium"}
                anomaly_b = {"type": "suspected_duplicate", "message": message.format(other=row_a["row_number"]), "severity": "medium"}
                results.setdefault(row_a["row_number"], []).append(anomaly_a)
                results.setdefault(row_b["row_number"], []).append(anomaly_b)

    return results


def detect_settlement_pattern(row_data):
    """
    A single-recipient split_with (not the payer themselves) is
    structurally a transfer, not a shared expense. Checks BOTH the
    description and notes fields for explicit repayment language,
    since the source data sometimes puts that language directly in
    the description (e.g. "Rohan paid Aisha back") rather than notes.
    """
    split_with_raw = row_data.get("split_with") or ""
    participants = [name.strip() for name in split_with_raw.split(";") if name.strip()]
    payer = (row_data.get("paid_by") or "").strip()

    if len(participants) != 1:
        return []
    if participants[0].lower() == payer.lower():
        return []

    combined_text = f"{row_data.get('description') or ''} {row_data.get('notes') or ''}".lower()
    words = combined_text.split()
    is_explicit = (
        ("paid" in words and "back" in words)
        or "repaid" in combined_text
        or "reimburse" in combined_text
    )

    if is_explicit:
        return [{
            "type": "settlement_misclassified",
            "message": (
                f"'{row_data.get('description')}' looks like a direct payment from "
                f"{payer} to {participants[0]}, not a shared expense - will be recorded "
                f"as a settlement instead of an expense."
            ),
            "severity": "medium",
        }]
    else:
        return [{
            "type": "possible_settlement",
            "message": (
                f"'{row_data.get('description')}' has only one participant ({participants[0]}) "
                f"besides the payer - may be a direct payment rather than a shared expense, "
                f"but isn't explicit enough to auto-reclassify. Needs manual confirmation."
            ),
            "severity": "medium",
        }]
    
def _parse_semicolon_pairs(raw_string):
    """
    Parses strings like "Aisha 30; Rohan 30; Priya 30; Meera 20" into
    [("Aisha", "30"), ("Rohan", "30"), ...]. Used for both percentage
    and share split_details, which share this same "Name number;
    Name number" format in the source data.
    """
    if not raw_string:
        return []
    pairs = []
    for chunk in raw_string.split(";"):
        chunk = chunk.strip()
        if not chunk:
            continue
        parts = chunk.rsplit(" ", 1)
        if len(parts) == 2:
            name, value = parts
            pairs.append((name.strip(), value.strip()))
    return pairs


def detect_percentage_mismatch(row_data):
    """
    Percentages in split_details must sum to exactly 100. We do NOT
    auto-normalize a mismatched sum (e.g. rescaling 110% down to
    100%) - see DECISIONS.md: rescaling silently changes what each
    person agreed to pay, and we have no way to know which single
    value was the actual typo. Always flagged for manual review.
    """
    if row_data.get("split_type") != "percentage":
        return []

    pairs = _parse_semicolon_pairs(row_data.get("split_details"))
    if not pairs:
        return []

    try:
        total = sum(float(value.rstrip("%")) for _, value in pairs)
    except ValueError:
        return [{
            "type": "percentage_unparseable",
            "message": f"Could not parse percentage values from split_details: '{row_data.get('split_details')}'.",
            "severity": "high",
        }]

    if abs(total - 100) > 0.01:
        breakdown = ", ".join(f"{name} {value}%" for name, value in pairs)
        return [{
            "type": "percentage_mismatch",
            "message": (
                f"Percentages sum to {total}%, not 100% ({breakdown}). "
                f"Cannot determine which value is incorrect - needs manual correction."
            ),
            "severity": "high",
        }]
    return []


def detect_non_member_participant(row_data, group_members):
    """
    Every name in split_with must resolve to an actual group member.
    A name that doesn't (e.g. "Dev's friend Kabir") means the split
    can't be validly computed - we don't know how to divide the
    expense among people the group doesn't recognize.
    """
    split_with_raw = row_data.get("split_with") or ""
    participant_names = [name.strip() for name in split_with_raw.split(";") if name.strip()]

    unresolved = [
        name for name in participant_names
        if resolve_member(name, group_members) is None
    ]

    if unresolved:
        return [{
            "type": "non_member_participant",
            "message": (
                f"split_with includes {', '.join(unresolved)}, who don't match any "
                f"group member. The split can't be computed until this is resolved - "
                f"either add them as a member or remove them from this expense."
            ),
            "severity": "high",
        }]
    return []


def detect_negative_amount(row_data):
    """
    A negative amount could be a legitimate refund/reversal, or a
    data-entry error. We use the description/notes as a weak signal:
    explicit "refund" language gets a low-severity informational flag
    (proceeds as a negative adjustment); anything else is flagged high
    severity for manual review, since we can't tell those two cases
    apart with confidence otherwise.
    """
    amount = row_data.get("amount")
    if amount is None or amount >= 0:
        return []

    combined_text = f"{row_data.get('description') or ''} {row_data.get('notes') or ''}".lower()
    is_refund = "refund" in combined_text

    if is_refund:
        return [{
            "type": "negative_amount_refund",
            "message": f"Negative amount ({amount}) with 'refund' in the description - treated as a legitimate reversal.",
            "severity": "low",
        }]
    else:
        return [{
            "type": "negative_amount_unexplained",
            "message": f"Negative amount ({amount}) with no indication it's a refund - could be a data-entry error. Needs manual confirmation.",
            "severity": "high",
        }]


def detect_missing_currency(row_data):
    """
    Currency field empty. The import service will default this to the
    group's base currency (INR) when committing, but that default is
    always surfaced here, never applied silently.
    """
    if not row_data.get("currency"):
        return [{
            "type": "missing_currency",
            "message": "Currency field is empty - will default to INR unless corrected.",
            "severity": "medium",
        }]
    return []