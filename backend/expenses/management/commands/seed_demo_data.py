"""
Seeds the database with a realistic demo Flatmates group: memberships
with real join/leave dates (Meera left end of March, Sam joined mid-
April), and one expense per split type, generated via split_service.py
so the ExpenseSplit rows are calculated the same way the real API
will calculate them - not hand-typed test data that could drift from
the actual algorithm.

Usernames are capitalized (Aisha, Rohan, ...) to match the real
casing used throughout the actual expenses_export.xlsx data - this
matters for the import pipeline's name-normalization detector, which
compares CSV payer names against real group member usernames.

Safe to re-run: deletes existing Flatmates data in dependency order
(splits/expenses/settlements before memberships, since those are
PROTECT-ed foreign keys) then recreates it from scratch.

Usage: python manage.py seed_demo_data
"""

from decimal import Decimal

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.db import transaction

from groups.models import Group, GroupMembership
from expenses.models import Expense, ExpenseSplit, Settlement, SplitType, Currency, ExpenseSource
from expenses.services.split_service import (
    calculate_equal_split,
    calculate_unequal_split,
    calculate_share_split,
)

MEMBER_TIMELINE = {
    "Aisha": ("2026-02-01", None),
    "Rohan": ("2026-02-01", None),
    "Priya": ("2026-02-01", None),
    "Meera": ("2026-02-01", "2026-03-31"),  # moved out end of March
    # Dev's actual window derived from the real CSV: appears in a
    # casual Feb 8 dinner ("Dev visiting for the weekend") through
    # the Goa trip which runs through March 12.
    "Dev": ("2026-02-08", "2026-03-12"),
    # Sam's shared-expense participation starts April 10 in the real
    # data; his April 8 deposit payment predates official membership,
    # which is fine - it's handled as a Settlement (a plain transfer),
    # not an Expense split, so it doesn't require active membership.
    "Sam": ("2026-04-10", None),
}


class Command(BaseCommand):
    help = "Seeds a demo Flatmates group with realistic membership timeline and sample expenses."

    @transaction.atomic
    def handle(self, *args, **options):
        # Clean slate for the demo group only. Must delete in dependency
        # order - Expense/ExpenseSplit/Settlement PROTECT their
        # GroupMembership FKs, so those have to go first, or the
        # cascade from deleting Group hits the PROTECT and fails.
        existing_group = Group.objects.filter(name="Flatmates").first()
        if existing_group:
            ExpenseSplit.objects.filter(expense__group=existing_group).delete()
            Expense.objects.filter(group=existing_group).delete()
            Settlement.objects.filter(group=existing_group).delete()
            existing_group.delete()

        admin_user, _ = User.objects.get_or_create(
            username="admin", defaults={"is_staff": True, "is_superuser": True}
        )

        group = Group.objects.create(name="Flatmates", created_by=admin_user)
        self.stdout.write(self.style.SUCCESS(f"Created group: {group}"))

        memberships = {}
        for username, (joined_at, left_at) in MEMBER_TIMELINE.items():
            user, _ = User.objects.get_or_create(username=username)
            membership = GroupMembership.objects.create(
                group=group, user=user, joined_at=joined_at, left_at=left_at
            )
            memberships[username] = membership
            self.stdout.write(f"  Added member: {membership}")

        # --- Equal split: Groceries, active members only on this date ---
        active_ids = ["Aisha", "Rohan", "Priya", "Meera"]  # Meera still active mid-Feb
        expense1 = Expense.objects.create(
            group=group,
            description="Groceries - BigBasket",
            paid_by=memberships["Aisha"],
            date="2026-02-15",
            currency=Currency.INR,
            amount=Decimal("900.00"),
            amount_base_currency=Decimal("900.00"),
            split_type=SplitType.EQUAL,
            source=ExpenseSource.MANUAL,
        )
        shares = calculate_equal_split(
            expense1.amount, [memberships[u].id for u in active_ids]
        )
        for member_id, share in shares.items():
            ExpenseSplit.objects.create(
                expense=expense1, member_id=member_id, share_amount=share
            )
        self.stdout.write(self.style.SUCCESS(f"Created equal-split expense: {expense1}"))

        # --- Unequal split: Electricity ---
        expense2 = Expense.objects.create(
            group=group,
            description="Electricity bill",
            paid_by=memberships["Rohan"],
            date="2026-02-20",
            currency=Currency.INR,
            amount=Decimal("1000.00"),
            amount_base_currency=Decimal("1000.00"),
            split_type=SplitType.UNEQUAL,
            source=ExpenseSource.MANUAL,
        )
        unequal_amounts = {
            memberships["Rohan"].id: Decimal("400.00"),
            memberships["Priya"].id: Decimal("300.00"),
            memberships["Aisha"].id: Decimal("300.00"),
        }
        shares = calculate_unequal_split(expense2.amount, unequal_amounts)
        for member_id, share in shares.items():
            ExpenseSplit.objects.create(
                expense=expense2, member_id=member_id, share_amount=share
            )
        self.stdout.write(self.style.SUCCESS(f"Created unequal-split expense: {expense2}"))

        # --- Share split: Trip fuel (Dev is active only during the trip window) ---
        expense3 = Expense.objects.create(
            group=group,
            description="Trip fuel",
            paid_by=memberships["Dev"],
            date="2026-02-18",
            currency=Currency.INR,
            amount=Decimal("3000.00"),
            amount_base_currency=Decimal("3000.00"),
            split_type=SplitType.SHARE,
            source=ExpenseSource.MANUAL,
        )
        share_units = {
            memberships["Aisha"].id: 1,
            memberships["Rohan"].id: 2,
            memberships["Priya"].id: 1,
        }
        shares = calculate_share_split(expense3.amount, share_units)
        for member_id, share in shares.items():
            ExpenseSplit.objects.create(
                expense=expense3, member_id=member_id, share_amount=share
            )
        self.stdout.write(self.style.SUCCESS(f"Created share-split expense: {expense3}"))

        # --- A settlement: Rohan pays Aisha back ---
        Settlement.objects.create(
            group=group,
            paid_by=memberships["Rohan"],
            paid_to=memberships["Aisha"],
            amount=Decimal("200.00"),
            currency=Currency.INR,
            date="2026-02-25",
            source=ExpenseSource.MANUAL,
        )
        self.stdout.write(self.style.SUCCESS("Created settlement: Rohan -> Aisha 200.00"))

        self.stdout.write(self.style.SUCCESS("\nDemo data seeded successfully."))