"""
Seeds the database with a realistic demo Flatmates group: memberships
with real join/leave dates (Meera left end of March, Sam joined mid-
April), and one expense per split type, generated via split_service.py
so the ExpenseSplit rows are calculated the same way the real API
will calculate them — not hand-typed test data that could drift from
the actual algorithm.

Safe to re-run: wipes and recreates only the "Flatmates" demo data,
does not touch unrelated groups.

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
    "aisha": ("2026-02-01", None),
    "rohan": ("2026-02-01", None),
    "priya": ("2026-02-01", None),
    "meera": ("2026-02-01", "2026-03-31"),  # moved out end of March
    "dev": ("2026-02-15", "2026-02-20"),    # joined only for the trip
    "sam": ("2026-04-15", None),            # moved in mid-April
}


class Command(BaseCommand):
    help = "Seeds a demo Flatmates group with realistic membership timeline and sample expenses."

    @transaction.atomic
    def handle(self, *args, **options):
        # Clean slate for the demo group only
        Group.objects.filter(name="Flatmates").delete()

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
        active_ids = ["aisha", "rohan", "priya", "meera"]  # Meera still active mid-Feb
        expense1 = Expense.objects.create(
            group=group,
            description="Groceries - BigBasket",
            paid_by=memberships["aisha"],
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
            paid_by=memberships["rohan"],
            date="2026-02-20",
            currency=Currency.INR,
            amount=Decimal("1000.00"),
            amount_base_currency=Decimal("1000.00"),
            split_type=SplitType.UNEQUAL,
            source=ExpenseSource.MANUAL,
        )
        unequal_amounts = {
            memberships["rohan"].id: Decimal("400.00"),
            memberships["priya"].id: Decimal("300.00"),
            memberships["aisha"].id: Decimal("300.00"),
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
            paid_by=memberships["dev"],
            date="2026-02-18",
            currency=Currency.INR,
            amount=Decimal("3000.00"),
            amount_base_currency=Decimal("3000.00"),
            split_type=SplitType.SHARE,
            source=ExpenseSource.MANUAL,
        )
        share_units = {
            memberships["aisha"].id: 1,
            memberships["rohan"].id: 2,
            memberships["priya"].id: 1,
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
            paid_by=memberships["rohan"],
            paid_to=memberships["aisha"],
            amount=Decimal("200.00"),
            currency=Currency.INR,
            date="2026-02-25",
            source=ExpenseSource.MANUAL,
        )
        self.stdout.write(self.style.SUCCESS("Created settlement: Rohan -> Aisha 200.00"))

        self.stdout.write(self.style.SUCCESS("\nDemo data seeded successfully."))