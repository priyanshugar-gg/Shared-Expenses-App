import django
import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from imports.services.csv_parser import parse_expense_file
from imports.services.anomaly_detector import (
    detect_exact_duplicates, detect_suspected_duplicates, detect_settlement_pattern
)

rows = parse_expense_file("../sample_data/expenses_export.xlsx")

exact_dupes = detect_exact_duplicates(rows)
suspected_dupes = detect_suspected_duplicates(rows)

print("--- Exact duplicates ---")
for row_number, anomalies in exact_dupes.items():
    print(row_number, [a["message"] for a in anomalies])

print("--- Suspected duplicates ---")
for row_number, anomalies in suspected_dupes.items():
    print(row_number, [a["type"] for a in anomalies])

print("--- Settlement patterns ---")
for row in rows:
    anomalies = detect_settlement_pattern(row["data"])
    if anomalies:
        print(row["row_number"], row["data"].get("description"), "->", [a["type"] for a in anomalies])