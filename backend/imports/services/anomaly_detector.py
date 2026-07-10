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