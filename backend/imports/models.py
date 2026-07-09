from django.conf import settings
from django.db import models

from groups.models import Group
from expenses.models import Expense, Settlement


class ImportBatchStatus(models.TextChoices):
    SCANNING = "scanning", "Scanning"
    PENDING_REVIEW = "pending_review", "Pending review"
    COMMITTED = "committed", "Committed"
    CANCELLED = "cancelled", "Cancelled"


class ImportBatch(models.Model):
    """
    One upload event. Nothing in ImportRow becomes a real Expense/
    Settlement until the batch is explicitly committed - this is the
    structural answer to "never silently modify data": the scan phase
    only ever writes to ImportRow, a staging table, never to the real
    ledger tables.
    """
    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name="import_batches")
    file_name = models.CharField(max_length=255)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    status = models.CharField(
        max_length=20, choices=ImportBatchStatus.choices, default=ImportBatchStatus.SCANNING
    )
    total_rows = models.IntegerField(default=0)

    class Meta:
        ordering = ["-uploaded_at"]

    def __str__(self):
        return f"Import {self.file_name} into {self.group.name} ({self.status})"


class ProposedAction(models.TextChoices):
    CREATE_EXPENSE = "create_expense", "Create expense"
    CREATE_SETTLEMENT = "create_settlement", "Create settlement"
    SKIP = "skip", "Skip (duplicate)"
    NEEDS_MANUAL_REVIEW = "needs_manual_review", "Needs manual review"


class RowResolution(models.TextChoices):
    APPROVED = "approved", "Approved"
    REJECTED = "rejected", "Rejected"
    EDITED = "edited", "Edited and approved"


class ImportRow(models.Model):
    """
    One staged CSV row. raw_data is written once at scan time and never
    modified afterward - it is the permanent, honest record of exactly
    what the source file contained. Any correction a human makes (e.g.
    supplying a missing payer, or the app auto-excluding an inactive
    member) is recorded separately in resolved_data, so raw_data vs
    resolved_data is always a clean, auditable diff.

    resolution stays null until a human (or an explicit auto-approve
    rule we've documented) decides what happens to this row - nothing
    reaches Expense/Settlement before that.
    """
    batch = models.ForeignKey(ImportBatch, on_delete=models.CASCADE, related_name="rows")
    row_number = models.IntegerField()

    raw_data = models.JSONField()
    resolved_data = models.JSONField(null=True, blank=True)

    anomalies = models.JSONField(default=list)
    proposed_action = models.CharField(max_length=30, choices=ProposedAction.choices)

    resolution = models.CharField(
        max_length=10, choices=RowResolution.choices, null=True, blank=True
    )
    resolution_notes = models.TextField(blank=True)

    resulting_expense = models.ForeignKey(
        Expense, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    resulting_settlement = models.ForeignKey(
        Settlement, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )

    class Meta:
        ordering = ["row_number"]
        constraints = [
            models.UniqueConstraint(
                fields=["batch", "row_number"], name="unique_row_number_per_batch"
            )
        ]

    def __str__(self):
        return f"Row {self.row_number} of batch {self.batch_id} ({self.proposed_action})"

    def has_high_severity_anomaly(self):
        return any(a.get("severity") == "high" for a in self.anomalies)