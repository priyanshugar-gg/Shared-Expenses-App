"""
Split calculation service.

Pure calculation logic — no Django ORM writes happen in this file.
Each function takes an amount and participant data, and returns a
dict of {group_membership_id: Decimal share_amount} that sums EXACTLY
to the input amount. Callers (views, import pipeline) are responsible
for turning that dict into actual ExpenseSplit rows.

Kept separate from models.py and views.py deliberately: this logic
has no dependency on HTTP or the database, so it can be unit tested
directly and reused identically by both the manual "create expense"
API and the CSV import pipeline.
"""

from decimal import Decimal, ROUND_DOWN


class SplitValidationError(Exception):
    """Raised when the input data can't produce a valid split."""
    pass


def _distribute_remainder(amount: Decimal, raw_shares: dict) -> dict:
    """
    Largest remainder method.

    raw_shares: {member_id: exact Decimal share, before rounding}
    Returns: {member_id: Decimal share, rounded to 2dp, summing exactly to `amount`}

    Why this exists: naive per-share rounding can make the split total
    drift away from the actual expense amount by a few paise. This
    guarantees the rounded splits always reconcile exactly.
    """
    floored = {}
    remainders = {}
    for member_id, raw in raw_shares.items():
        floor_value = raw.quantize(Decimal("0.01"), rounding=ROUND_DOWN)
        floored[member_id] = floor_value
        remainders[member_id] = raw - floor_value

    leftover_paise = amount - sum(floored.values())
    # leftover_paise should be a small non-negative multiple of 0.01
    leftover_units = int((leftover_paise / Decimal("0.01")).to_integral_value())

    # Give the extra paise to whoever lost the most in rounding down,
    # breaking ties by member_id for determinism (same input -> same output,
    # important for tests and for the import pipeline being reproducible).
    ordered_members = sorted(
        remainders.keys(), key=lambda m: (-remainders[m], m)
    )

    result = dict(floored)
    for i in range(leftover_units):
        member_id = ordered_members[i % len(ordered_members)]
        result[member_id] += Decimal("0.01")

    return result


def calculate_equal_split(amount: Decimal, member_ids: list) -> dict:
    """Split `amount` evenly across all member_ids."""
    if not member_ids:
        raise SplitValidationError("Equal split requires at least one participant.")

    raw_share = amount / len(member_ids)
    raw_shares = {member_id: raw_share for member_id in member_ids}
    return _distribute_remainder(amount, raw_shares)


def calculate_share_split(amount: Decimal, shares_by_member: dict) -> dict:
    """
    shares_by_member: {member_id: Decimal or int share_units}
    e.g. {aisha: 1, rohan: 2, priya: 1} -> Rohan gets double Aisha's/Priya's cut.
    """
    total_units = sum(Decimal(units) for units in shares_by_member.values())
    if total_units <= 0:
        raise SplitValidationError("Share split requires total units greater than zero.")

    raw_shares = {
        member_id: amount * Decimal(units) / total_units
        for member_id, units in shares_by_member.items()
    }
    return _distribute_remainder(amount, raw_shares)


def calculate_percentage_split(amount: Decimal, percentages_by_member: dict) -> dict:
    """
    percentages_by_member: {member_id: Decimal percentage}, must sum to exactly 100.

    Deliberately strict: we do NOT auto-normalize a percentage split that
    doesn't sum to 100 (e.g. the CSV's 110% rent split). Silently rescaling
    someone's declared percentage changes what they agreed to pay, and we
    have no way to know which number was the actual typo. That row gets
    flagged for manual review by the import pipeline instead.
    """
    total_percentage = sum(percentages_by_member.values())
    if total_percentage != Decimal("100"):
        raise SplitValidationError(
            f"Percentages must sum to exactly 100, got {total_percentage}."
        )

    raw_shares = {
        member_id: amount * pct / Decimal("100")
        for member_id, pct in percentages_by_member.items()
    }
    return _distribute_remainder(amount, raw_shares)


def calculate_unequal_split(amount: Decimal, amounts_by_member: dict) -> dict:
    """
    amounts_by_member: {member_id: Decimal explicit_amount}, must sum exactly
    to `amount`. No rounding needed here — the caller already specified
    exact figures; we only validate they add up.
    """
    total = sum(amounts_by_member.values())
    if total != amount:
        raise SplitValidationError(
            f"Unequal split amounts sum to {total}, expected {amount}."
        )
    return dict(amounts_by_member)