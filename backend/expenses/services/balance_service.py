"""
Balance calculation service.

Three responsibilities, deliberately kept separate:
  1. calculate_group_balances  - the raw net number per member
  2. get_member_balance_trace  - the itemized breakdown behind that number
  3. simplify_debts            - turns raw balances into minimal "who pays whom"

No Django views/serializers logic here - this operates on model
querysets directly and returns plain Python data structures, so it's
testable without spinning up HTTP requests, and reusable by both the
API layer and (later) the import report.
"""

from decimal import Decimal
from collections import defaultdict

from expenses.models import Expense, ExpenseSplit, Settlement


def calculate_group_balances(group) -> dict:
    """
    Returns {membership_id: Decimal net_balance} for every membership
    that has ever appeared in this group's expenses/splits/settlements.

    Sign convention:
      positive = the group owes this member money (net creditor)
      negative = this member owes the group money (net debtor)
    """
    balances = defaultdict(lambda: Decimal("0.00"))

    # Credit whoever paid each expense, in full, in base currency.
    for expense in Expense.objects.filter(group=group).select_related("paid_by"):
        balances[expense.paid_by_id] += expense.amount_base_currency

    # Debit everyone for their own share of every expense.
    for split in ExpenseSplit.objects.filter(expense__group=group).select_related("member"):
        balances[split.member_id] -= split.share_amount

    # Settlements: payer's balance moves up (debt discharged),
    # receiver's balance moves down (they've now actually been paid).
    for settlement in Settlement.objects.filter(group=group):
        balances[settlement.paid_by_id] += settlement.amount
        balances[settlement.paid_to_id] -= settlement.amount

    return dict(balances)


def get_member_balance_trace(group, membership) -> dict:
    """
    Itemized breakdown for one member: every expense they paid, every
    expense they owe a share of, and every settlement they were party
    to - the literal line items that sum to their net balance.

    This is the direct answer to "if the app says I owe ₹2,300, show
    me exactly which expenses make that up."
    """
    paid = list(
        Expense.objects.filter(group=group, paid_by=membership)
        .values("id", "description", "date", "amount_base_currency")
    )
    owed = list(
        ExpenseSplit.objects.filter(expense__group=group, member=membership)
        .select_related("expense")
        .values("expense_id", "expense__description", "expense__date", "share_amount")
    )
    settlements_paid = list(
        Settlement.objects.filter(group=group, paid_by=membership)
        .values("id", "paid_to__user__username", "amount", "date")
    )
    settlements_received = list(
        Settlement.objects.filter(group=group, paid_to=membership)
        .values("id", "paid_by__user__username", "amount", "date")
    )

    total_paid = sum((e["amount_base_currency"] for e in paid), Decimal("0.00"))
    total_owed = sum((s["share_amount"] for s in owed), Decimal("0.00"))
    total_settled_paid = sum((s["amount"] for s in settlements_paid), Decimal("0.00"))
    total_settled_received = sum((s["amount"] for s in settlements_received), Decimal("0.00"))

    net_balance = total_paid - total_owed + total_settled_paid - total_settled_received

    return {
        "expenses_paid": paid,
        "expense_shares_owed": owed,
        "settlements_paid": settlements_paid,
        "settlements_received": settlements_received,
        "net_balance": net_balance,
    }


def simplify_debts(balances: dict) -> list:
    """
    Given {membership_id: net_balance}, returns the MINIMUM number of
    transactions that settles everyone to zero, as a list of
    {from_id, to_id, amount} dicts.

    Uses exact backtracking (not a greedy heap heuristic), which finds
    the true minimum rather than an approximation. This is only
    tractable because our group sizes are small (a handful of
    roommates, not hundreds of users) - for a general-purpose ledger
    product at scale, a greedy approach would be the right tradeoff
    instead. Worth naming directly if asked "why not greedy" or
    "does this scale."
    """
    amounts = {
        member_id: int((balance * 100).to_integral_value())
        for member_id, balance in balances.items()
        if balance != 0
    }
    ids = list(amounts.keys())
    values = [amounts[i] for i in ids]

    best_transactions = None

    def backtrack(index, transactions):
        nonlocal best_transactions

        # Skip members already fully resolved by an earlier transaction
        while index < len(values) and values[index] == 0:
            index += 1

        if index == len(values):
            if best_transactions is None or len(transactions) < len(best_transactions):
                best_transactions = list(transactions)
            return

        # Prune: can't possibly beat the best solution found so far
        if best_transactions is not None and len(transactions) >= len(best_transactions):
            return

        for j in range(index + 1, len(values)):
            if values[j] != 0 and (values[j] < 0) != (values[index] < 0):
                # Transfer ALL of values[index] onto j - index is now
                # considered resolved, even though its stored value isn't
                # literally 0 (we simply never look at it again).
                values[j] += values[index]
                transactions.append((index, j, values[index]))

                backtrack(index + 1, transactions)

                transactions.pop()
                values[j] -= values[index]

    backtrack(0, [])

    result = []
    for i, j, amount in (best_transactions or []):
        if amount < 0:
            from_id, to_id, cents = ids[i], ids[j], -amount
        else:
            from_id, to_id, cents = ids[j], ids[i], amount
        result.append({
            "from_id": from_id,
            "to_id": to_id,
            "amount": Decimal(cents) / 100,
        })

    return result