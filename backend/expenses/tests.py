from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase

from groups.models import Group, GroupMembership
from expenses.models import Expense, ExpenseSplit, Settlement, SplitType, Currency, ExpenseSource
from expenses.services.split_service import calculate_equal_split
from expenses.services.balance_service import calculate_group_balances, simplify_debts


class BalanceCalculationTests(TestCase):
    """
    Rebuilds the exact seed_demo_data scenario in an isolated test
    database, so these numbers are locked in permanently - if a future
    change to balance_service.py breaks this math, this test fails
    immediately instead of the bug surfacing silently later.
    """

    def setUp(self):
        admin = User.objects.create(username="admin")
        self.group = Group.objects.create(name="Flatmates", created_by=admin)

        self.users = {}
        self.memberships = {}
        for username in ["aisha", "rohan", "priya", "meera", "dev"]:
            user = User.objects.create(username=username)
            self.users[username] = user
            self.memberships[username] = GroupMembership.objects.create(
                group=self.group, user=user, joined_at="2026-02-01"
            )

        # Groceries: Aisha paid 900, split equally among aisha/rohan/priya/meera
        expense1 = Expense.objects.create(
            group=self.group,
            description="Groceries",
            paid_by=self.memberships["aisha"],
            date="2026-02-15",
            currency=Currency.INR,
            amount=Decimal("900.00"),
            amount_base_currency=Decimal("900.00"),
            split_type=SplitType.EQUAL,
            source=ExpenseSource.MANUAL,
        )
        shares = calculate_equal_split(
            expense1.amount,
            [self.memberships[u].id for u in ["aisha", "rohan", "priya", "meera"]],
        )
        for member_id, share in shares.items():
            ExpenseSplit.objects.create(expense=expense1, member_id=member_id, share_amount=share)

        # Electricity: Rohan paid 1000, unequal split
        expense2 = Expense.objects.create(
            group=self.group,
            description="Electricity",
            paid_by=self.memberships["rohan"],
            date="2026-02-20",
            currency=Currency.INR,
            amount=Decimal("1000.00"),
            amount_base_currency=Decimal("1000.00"),
            split_type=SplitType.UNEQUAL,
            source=ExpenseSource.MANUAL,
        )
        for username, amount in [("rohan", "400.00"), ("priya", "300.00"), ("aisha", "300.00")]:
            ExpenseSplit.objects.create(
                expense=expense2, member=self.memberships[username], share_amount=Decimal(amount)
            )

        # Trip fuel: Dev paid 3000, share split aisha:1 rohan:2 priya:1
        expense3 = Expense.objects.create(
            group=self.group,
            description="Trip fuel",
            paid_by=self.memberships["dev"],
            date="2026-02-18",
            currency=Currency.INR,
            amount=Decimal("3000.00"),
            amount_base_currency=Decimal("3000.00"),
            split_type=SplitType.SHARE,
            source=ExpenseSource.MANUAL,
        )
        for username, amount in [("aisha", "750.00"), ("rohan", "1500.00"), ("priya", "750.00")]:
            ExpenseSplit.objects.create(
                expense=expense3, member=self.memberships[username], share_amount=Decimal(amount)
            )

        # Settlement: Rohan pays Aisha 200
        Settlement.objects.create(
            group=self.group,
            paid_by=self.memberships["rohan"],
            paid_to=self.memberships["aisha"],
            amount=Decimal("200.00"),
            currency=Currency.INR,
            date="2026-02-25",
            source=ExpenseSource.MANUAL,
        )

    def test_individual_balances_match_hand_calculation(self):
        balances = calculate_group_balances(self.group)

        self.assertEqual(balances[self.memberships["rohan"].id], Decimal("-925.00"))
        self.assertEqual(balances[self.memberships["dev"].id], Decimal("3000.00"))
        self.assertEqual(balances[self.memberships["aisha"].id], Decimal("-575.00"))
        self.assertEqual(balances[self.memberships["priya"].id], Decimal("-1275.00"))
        self.assertEqual(balances[self.memberships["meera"].id], Decimal("-225.00"))

    def test_balances_always_sum_to_zero(self):
        """
        A balanced ledger must always net to zero - every rupee
        credited to a payer is debited from someone's share. If this
        ever fails, it means the ledger itself is broken, not just a
        display/rounding issue.
        """
        balances = calculate_group_balances(self.group)
        self.assertEqual(sum(balances.values()), Decimal("0.00"))

    def test_simplify_debts_settles_everyone_to_zero(self):
        """
        This is the exact test that would have caught the original
        cascading-index bug: it doesn't just check the transaction
        count, it replays every transaction and asserts each person's
        balance actually reaches zero afterward.
        """
        balances = calculate_group_balances(self.group)
        transactions = simplify_debts(balances)

        self.assertGreater(len(transactions), 0, "simplify_debts returned no transactions")

        running_balances = dict(balances)
        for t in transactions:
            running_balances[t["from_id"]] += t["amount"]
            running_balances[t["to_id"]] -= t["amount"]

        for member_id, final_balance in running_balances.items():
            self.assertEqual(
                final_balance, Decimal("0.00"),
                f"Member {member_id} did not reach zero balance after settlement",
            )

    def test_simplify_debts_uses_minimum_transactions(self):
        """
        With 5 people all holding distinct non-zero balances and no
        subset summing to zero on its own, the true minimum is n-1 = 4
        transactions. This asserts we get the OPTIMAL count, not just
        "a" valid settlement plan.
        """
        balances = calculate_group_balances(self.group)
        transactions = simplify_debts(balances)
        self.assertEqual(len(transactions), 4)