import django, os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from expenses.models import Expense as ExpenseModel, Settlement as SettlementModel
ExpenseModel.objects.filter(source="import").delete()
SettlementModel.objects.filter(source="import").delete()
from imports.models import ImportBatch as ImportBatchModel
ImportBatchModel.objects.all().delete()
print("Cleared previous import data.\n")
from django.contrib.auth.models import User
from groups.models import Group
from imports.services.import_service import scan_csv, commit_batch
from imports.models import ImportRow, RowResolution

group = Group.objects.get(name="Flatmates")
admin = User.objects.get(username="admin")

batch = scan_csv("../sample_data/expenses_export.xlsx", "expenses_export.xlsx", group, admin)
print(f"Batch {batch.id}: {batch.total_rows} rows, status={batch.status}")

auto_approved = batch.rows.filter(resolution=RowResolution.APPROVED).count()
needs_review = batch.rows.filter(resolution__isnull=True).count()
print(f"Auto-approved: {auto_approved}, needs review: {needs_review}")

print("\n--- Rows needing review ---")
for row in batch.rows.filter(resolution__isnull=True):
    print(row.row_number, row.proposed_action, [a["type"] for a in row.anomalies])

# Approve every needs_manual_review row that isn't a genuine data
# problem (skip the two "hold for human" duplicate rows on purpose,
# to prove skip/review rows correctly stay OUT of the ledger).
for row in batch.rows.filter(resolution__isnull=True, proposed_action__in=["create_expense", "create_settlement"]):
    row.resolution = RowResolution.APPROVED
    row.save()

commit_batch(batch)
print(f"\nBatch committed. Status: {batch.status}")

from expenses.models import Expense, Settlement
print("Expenses created from this import:", Expense.objects.filter(source="import").count())
print("Settlements created from this import:", Settlement.objects.filter(source="import").count())