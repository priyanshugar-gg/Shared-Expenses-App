import django
import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from groups.models import Group
group = Group.objects.get(name="Flatmates")
members = list(group.memberships.select_related("user").all())

from imports.services.anomaly_detector import (
    detect_exact_duplicates, detect_suspected_duplicates, detect_settlement_pattern,
    detect_percentage_mismatch, detect_non_member_participant, detect_negative_amount, detect_missing_currency,
)

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

print("--- Percentage mismatches ---")
for row in rows:
    anomalies = detect_percentage_mismatch(row["data"])
    if anomalies:
        print(row["row_number"], row["data"].get("description"), "->", [a["type"] for a in anomalies])

print("--- Non-member participants ---")
for row in rows:
    anomalies = detect_non_member_participant(row["data"], members)
    if anomalies:
        print(row["row_number"], row["data"].get("description"), "->", [a["type"] for a in anomalies])

print("--- Negative amounts ---")
for row in rows:
    anomalies = detect_negative_amount(row["data"])
    if anomalies:
        print(row["row_number"], row["data"].get("description"), "->", [a["type"] for a in anomalies])

print("--- Missing currency ---")
for row in rows:
    anomalies = detect_missing_currency(row["data"])
    if anomalies:
        print(row["row_number"], row["data"].get("description"), "->", [a["type"] for a in anomalies])

from imports.services.anomaly_detector import (
    detect_ambiguous_date_format, detect_implausible_date, detect_zero_amount,
    detect_inactive_member_in_split, detect_split_type_details_contradiction,
    detect_excess_decimal_precision, compute_plausible_date_range,
)

date_range = compute_plausible_date_range(rows)
print("Computed plausible date range:", date_range)

print("--- Ambiguous date format ---")
for row in rows:
    anomalies = detect_ambiguous_date_format(row["data"])
    if anomalies:
        print(row["row_number"], row["data"].get("description"), "->", [a["type"] for a in anomalies])

print("--- Implausible dates ---")
for row in rows:
    anomalies = detect_implausible_date(row["data"], date_range)
    if anomalies:
        print(row["row_number"], row["data"].get("description"), row["data"].get("date"), "->", [a["type"] for a in anomalies])

print("--- Zero amount ---")
for row in rows:
    anomalies = detect_zero_amount(row["data"])
    if anomalies:
        print(row["row_number"], row["data"].get("description"), "->", [a["type"] for a in anomalies])

print("--- Inactive member in split ---")
for row in rows:
    anomalies = detect_inactive_member_in_split(row["data"], members)
    if anomalies:
        print(row["row_number"], row["data"].get("description"), "->", [a["type"] for a in anomalies])

print("--- Split type/details contradiction ---")
for row in rows:
    anomalies = detect_split_type_details_contradiction(row["data"])
    if anomalies:
        print(row["row_number"], row["data"].get("description"), "->", [a["type"] for a in anomalies])

print("--- Excess decimal precision ---")
for row in rows:
    anomalies = detect_excess_decimal_precision(row["data"])
    if anomalies:
        print(row["row_number"], row["data"].get("amount"), "->", [a["type"] for a in anomalies])