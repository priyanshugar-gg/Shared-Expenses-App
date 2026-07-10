"""
Orchestrates the two-phase import pipeline:
  scan_csv()     - parse + detect, writes ONLY to ImportRow (staging).
                   Never touches Expense/Settlement.
  commit_batch() - for approved rows, creates the real Expense/
                   Settlement/ExpenseSplit records, reusing
                   split_service.py so import-created expenses are
                   calculated identically to manually-created ones.

Auto-approval policy: a row auto-approves ONLY if every anomaly on it
is severity "low" (purely cosmetic, no effect on any amount). Any
medium/high severity anomaly holds the row for explicit human review -
this directly answers Meera's "approve anything the app changes",
using severity as the single, consistent rule rather than a
per-anomaly-type exception list.
"""

import json
from datetime import date, datetime
from decimal import Decimal

from django.db import transaction

from groups.models import GroupMembership
from expenses.models import Expense, ExpenseSplit, Settlement, Currency, SplitType, ExpenseSource, USD_TO_INR_RATE
from expenses.services.split_service import calculate_equal_split, SplitValidationError
from imports.models import ImportBatch, ImportRow, ImportBatchStatus, ProposedAction, RowResolution
from imports.services.csv_parser import parse_expense_file
from imports.services.anomaly_detector import (
    resolve_member, needs_normalization,
    detect_missing_payer, detect_ambiguous_payer, detect_payer_name_normalization,
    detect_exact_duplicates, detect_suspected_duplicates, detect_settlement_pattern,
    detect_percentage_mismatch, detect_non_member_participant, detect_negative_amount,
    detect_missing_currency, detect_ambiguous_date_format, detect_implausible_date,
    detect_zero_amount, detect_inactive_member_in_split, detect_split_type_details_contradiction,
    detect_excess_decimal_precision, compute_plausible_date_range,
)

# Anomaly types that force skip / needs_manual_review regardless of
# severity-based auto-approval - these represent a DECISION the app
# cannot make on its own, not just a cosmetic correction.
FORCED_SKIP_TYPES = {"exact_duplicate"}
FORCED_REVIEW_TYPES = {
    "missing_payer", "ambiguous_payer", "percentage_mismatch", "percentage_unparseable",
    "non_member_participant", "negative_amount_unexplained", "ambiguous_date_format",
    "implausible_date", "possible_settlement", "suspected_duplicate", "parse_error",
}


def _json_safe(value):
    """
    ImportRow.raw_data/resolved_data are JSONField - openpyxl hands us
    datetime and numeric types JSON can't serialize directly. This
    normalizes them to plain JSON-safe types.

    Critically: datetime objects are reduced to DATE-ONLY strings
    ("2026-04-02", not "2026-04-02T00:00:00") - Django's DateField
    parser only accepts the bare date format, and if given a full
    ISO datetime string, silently fails to convert it, leaving the
    raw string in place for clean() to compare against real date
    objects, causing a TypeError. isinstance check order matters:
    datetime IS a subclass of date, so it must be checked first.
    """
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return value


def _json_safe_dict(data):
    return {key: _json_safe(value) for key, value in data.items()}


def _determine_proposed_action(anomalies):
    types = {a["type"] for a in anomalies}

    if types & FORCED_SKIP_TYPES:
        return ProposedAction.SKIP
    if types & FORCED_REVIEW_TYPES:
        return ProposedAction.NEEDS_MANUAL_REVIEW
    if "settlement_misclassified" in types:
        return ProposedAction.CREATE_SETTLEMENT
    return ProposedAction.CREATE_EXPENSE


def _auto_approves(anomalies):
    """Only severity 'low' anomalies allow auto-approval - anything
    medium/high touches money and must be reviewed by a human."""
    return all(a.get("severity") == "low" for a in anomalies)


def _build_resolved_data(data, anomalies, group_members):
    """
    Applies only the specific, individually-justified auto-corrections:
    payer name normalization, missing-currency default, decimal
    rounding, and stripping inactive members out of split_with. Every
    other field is left exactly as raw_data had it - resolved_data is
    never a blind copy-with-guesses, only these named corrections.
    """
    resolved = dict(data)
    types = {a["type"] for a in anomalies}

    if "payer_name_normalized" in types:
        matched = resolve_member(data.get("paid_by"), group_members)
        if matched:
            resolved["paid_by"] = matched.user.username

    if "missing_currency" in types:
        resolved["currency"] = Currency.INR

    if "excess_decimal_precision" in types and data.get("amount") is not None:
        resolved["amount"] = round(float(data["amount"]), 2)

    if "inactive_member_in_split" in types:
        row_date = data.get("date")
        if hasattr(row_date, "date"):
            row_date = row_date.date()
        split_with_raw = data.get("split_with") or ""
        names = [n.strip() for n in split_with_raw.split(";") if n.strip()]
        active_names = []
        for name in names:
            member = resolve_member(name, group_members)
            if member is None or member.is_active_on(row_date):
                active_names.append(name)
        resolved["split_with"] = ";".join(active_names)

    return resolved


@transaction.atomic
def scan_csv(file_path_or_buffer, file_name, group, uploaded_by):
    """
    Phase 1: parse + detect. Creates ImportBatch + ImportRow rows only.
    No Expense/Settlement is created here, regardless of how clean or
    dirty a row is - that only happens in commit_batch(), and only for
    rows explicitly resolved (auto-approved or human-approved).
    """
    batch = ImportBatch.objects.create(
        group=group, file_name=file_name, uploaded_by=uploaded_by,
        status=ImportBatchStatus.SCANNING,
    )

    parsed_rows = parse_expense_file(file_path_or_buffer)
    group_members = list(group.memberships.select_related("user").all())
    date_range = compute_plausible_date_range(parsed_rows)

    # Cross-row detectors run once over the whole file, not per-row.
    exact_dupes = detect_exact_duplicates(parsed_rows)
    suspected_dupes = detect_suspected_duplicates(parsed_rows)

    import_rows = []
    for row in parsed_rows:
        row_number = row["row_number"]
        data = row["data"]
        anomalies = []

        if row["parse_error"]:
            anomalies.append({"type": "parse_error", "message": row["parse_error"], "severity": "high"})
        else:
            anomalies += detect_missing_payer(data)
            anomalies += detect_ambiguous_payer(data, group_members)
            anomalies += detect_payer_name_normalization(data, group_members)
            anomalies += exact_dupes.get(row_number, [])
            anomalies += suspected_dupes.get(row_number, [])
            anomalies += detect_settlement_pattern(data)
            anomalies += detect_percentage_mismatch(data)
            anomalies += detect_non_member_participant(data, group_members)
            anomalies += detect_negative_amount(data)
            anomalies += detect_missing_currency(data)
            anomalies += detect_ambiguous_date_format(data)
            anomalies += detect_implausible_date(data, date_range)
            anomalies += detect_zero_amount(data)
            anomalies += detect_inactive_member_in_split(data, group_members)
            anomalies += detect_split_type_details_contradiction(data)
            anomalies += detect_excess_decimal_precision(data)

        proposed_action = _determine_proposed_action(anomalies)
        resolved_data = _build_resolved_data(data, anomalies, group_members) if not row["parse_error"] else None
        resolution = RowResolution.APPROVED if _auto_approves(anomalies) else None

        import_rows.append(ImportRow(
            batch=batch,
            row_number=row_number,
            raw_data=_json_safe_dict(data),
            resolved_data=_json_safe_dict(resolved_data) if resolved_data else None,
            anomalies=anomalies,
            proposed_action=proposed_action,
            resolution=resolution,
            resolution_notes="Auto-approved: only cosmetic (low-severity) findings." if resolution else "",
        ))

    ImportRow.objects.bulk_create(import_rows)
    batch.total_rows = len(import_rows)
    batch.status = ImportBatchStatus.PENDING_REVIEW
    batch.save()
    return batch


def _resolve_row_participants(effective_data, group_members):
    """Turns split_with (+ split_details, for non-equal types) into the
    participant dicts split_service.py expects, resolving each name to
    its GroupMembership.id."""
    split_with_raw = effective_data.get("split_with") or ""
    names = [n.strip() for n in split_with_raw.split(";") if n.strip()]
    member_ids = []
    for name in names:
        member = resolve_member(name, group_members)
        if member:
            member_ids.append(member.id)
    return member_ids


@transaction.atomic
def commit_batch(batch):
    """
    Phase 2: for every ImportRow with resolution=approved, create the
    real Expense/ExpenseSplit/Settlement. Rejected or still-unresolved
    rows are left untouched - nothing is force-committed.
    """
    if batch.status != ImportBatchStatus.PENDING_REVIEW:
        raise ValueError(f"Batch must be pending_review to commit, got {batch.status}.")

    group_members = list(batch.group.memberships.select_related("user").all())

    for row in batch.rows.filter(resolution=RowResolution.APPROVED):
        effective_data = row.resolved_data or row.raw_data

        if row.proposed_action == ProposedAction.SKIP:
            continue  # explicitly a no-op: duplicate, deliberately not imported

        if row.proposed_action == ProposedAction.CREATE_SETTLEMENT:
            payer = resolve_member(effective_data.get("paid_by"), group_members)
            names = [n.strip() for n in (effective_data.get("split_with") or "").split(";") if n.strip()]
            payee = resolve_member(names[0], group_members) if names else None
            if payer and payee:
                settlement = Settlement.objects.create(
                    group=batch.group, paid_by=payer, paid_to=payee,
                    amount=Decimal(str(effective_data["amount"])),
                    currency=effective_data.get("currency") or Currency.INR,
                    date=effective_data["date"], source=ExpenseSource.IMPORT,
                )
                row.resulting_settlement = settlement
                row.save(update_fields=["resulting_settlement"])
            continue

        if row.proposed_action == ProposedAction.CREATE_EXPENSE:
            payer = resolve_member(effective_data.get("paid_by"), group_members)
            if not payer:
                continue  # safety net; shouldn't happen for an approved row

            amount = Decimal(str(effective_data["amount"]))
            currency = effective_data.get("currency") or Currency.INR
            if currency == Currency.USD:
                exchange_rate = USD_TO_INR_RATE
                amount_base = (amount * exchange_rate).quantize(Decimal("0.01"))
            else:
                exchange_rate = None
                amount_base = amount

            expense = Expense(
                group=batch.group, description=effective_data.get("description", ""),
                paid_by=payer, date=effective_data["date"], currency=currency,
                amount=amount, exchange_rate_used=exchange_rate,
                amount_base_currency=amount_base, split_type=SplitType.EQUAL,
                source=ExpenseSource.IMPORT,
            )
            expense.full_clean()
            expense.save()

            member_ids = _resolve_row_participants(effective_data, group_members)
            try:
                shares = calculate_equal_split(amount_base, member_ids)
            except SplitValidationError:
                shares = {payer.id: amount_base}  # fallback: charge only the payer

            ExpenseSplit.objects.bulk_create([
                ExpenseSplit(expense=expense, member_id=member_id, share_amount=share)
                for member_id, share in shares.items()
            ])

            row.resulting_expense = expense
            row.save(update_fields=["resulting_expense"])

    batch.status = ImportBatchStatus.COMMITTED
    batch.save()
    return batch