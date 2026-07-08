from decimal import Decimal
from django.core.exceptions import ValidationError
from django.db import models

from groups.models import Group, GroupMembership


class Currency(models.TextChoices):
    INR = "INR", "Indian Rupee"
    USD = "USD", "US Dollar"


class SplitType(models.TextChoices):
    EQUAL = "equal", "Equal"
    UNEQUAL = "unequal", "Unequal (explicit amounts)"
    PERCENTAGE = "percentage", "Percentage"
    SHARE = "share", "Share (weighted units)"


class ExpenseSource(models.TextChoices):
    MANUAL = "manual", "Entered manually"
    IMPORT = "import", "Created from CSV import"


# Fixed conversion rate used when no live FX API is available.
# Documented assumption (see DECISIONS.md) — a production version
# would call a live rate service and store the rate per-transaction-date.
USD_TO_INR_RATE = Decimal("83.00")


class Expense(models.Model):
    """
    One shared cost incurred by the group. Money math always happens
    in `amount_base_currency` (INR); `amount`/`currency` preserve
    exactly what was originally entered/imported, so a currency
    conversion is never silently baked in and lost.
    """
    group = models.ForeignKey(
        Group, on_delete=models.CASCADE, related_name="expenses"
    )
    description = models.CharField(max_length=255)
    paid_by = models.ForeignKey(
        GroupMembership, on_delete=models.PROTECT, related_name="expenses_paid"
    )
    date = models.DateField()

    currency = models.CharField(max_length=3, choices=Currency.choices)
    amount = models.DecimalField(max_digits=12, decimal_places=2)

    exchange_rate_used = models.DecimalField(
        max_digits=8, decimal_places=4, null=True, blank=True
    )
    amount_base_currency = models.DecimalField(max_digits=12, decimal_places=2)

    split_type = models.CharField(max_length=20, choices=SplitType.choices)
    notes = models.TextField(blank=True)

    source = models.CharField(
        max_length=10, choices=ExpenseSource.choices, default=ExpenseSource.MANUAL
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date", "-created_at"]

    def __str__(self):
        return f"{self.description} ({self.amount} {self.currency})"

    def clean(self):
        """
        Model-level validation: the payer must have been an active
        member of the group on the expense date. This is what stops
        a March expense from being attributed to a payer who joined
        in April, or vice versa.
        """
        if self.paid_by_id and self.date:
            if self.paid_by.group_id != self.group_id:
                raise ValidationError("Payer must belong to the same group as the expense.")
            if not self.paid_by.is_active_on(self.date):
                raise ValidationError(
                    f"{self.paid_by.user.username} was not an active member of "
                    f"the group on {self.date}."
                )


class ExpenseSplit(models.Model):
    """
    One row per participant per expense: exactly how much that person
    owes from that specific expense. This table is the direct, literal
    answer to "show me exactly which expenses make up my balance" —
    no aggregate math is ever the source of truth, only these rows.
    """
    expense = models.ForeignKey(
        Expense, on_delete=models.CASCADE, related_name="splits"
    )
    member = models.ForeignKey(
        GroupMembership, on_delete=models.PROTECT, related_name="expense_splits"
    )
    share_amount = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["expense", "member"], name="unique_split_per_member_per_expense"
            )
        ]

    def __str__(self):
        return f"{self.member.user.username} owes {self.share_amount} for {self.expense_id}"


class Settlement(models.Model):
    """
    A direct payment from one member to another that settles debt.
    Deliberately NOT an Expense subtype — a settlement is never split
    between participants, it's a plain transfer, so giving it its own
    table keeps Expense's split logic from needing special-case branches.
    """
    group = models.ForeignKey(
        Group, on_delete=models.CASCADE, related_name="settlements"
    )
    paid_by = models.ForeignKey(
        GroupMembership, on_delete=models.PROTECT, related_name="settlements_paid"
    )
    paid_to = models.ForeignKey(
        GroupMembership, on_delete=models.PROTECT, related_name="settlements_received"
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, choices=Currency.choices, default=Currency.INR)
    date = models.DateField()
    notes = models.TextField(blank=True)

    source = models.CharField(
        max_length=10, choices=ExpenseSource.choices, default=ExpenseSource.MANUAL
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date", "-created_at"]

    def __str__(self):
        return f"{self.paid_by.user.username} paid {self.paid_to.user.username} {self.amount}"

    def clean(self):
        if self.paid_by_id and self.paid_to_id and self.paid_by_id == self.paid_to_id:
            raise ValidationError("A member cannot settle a debt with themselves.")