from django.core.exceptions import ValidationError as DjangoValidationError
from decimal import Decimal, ROUND_HALF_UP

from rest_framework import serializers
from django.db import transaction

from groups.models import GroupMembership
from .models import Expense, ExpenseSplit, Settlement, Currency, SplitType, ExpenseSource, USD_TO_INR_RATE
from .services.split_service import (
    calculate_equal_split,
    calculate_unequal_split,
    calculate_percentage_split,
    calculate_share_split,
    SplitValidationError,
)


class ExpenseSplitSerializer(serializers.ModelSerializer):
    """
    Read-only. This is the literal data behind Rohan's "show me exactly
    which expenses make up my balance" - never recomputed on read,
    always the stored row.
    """
    member_username = serializers.CharField(source="member.user.username", read_only=True)

    class Meta:
        model = ExpenseSplit
        fields = ["id", "member", "member_username", "share_amount"]


class ExpenseSerializer(serializers.ModelSerializer):
    splits = ExpenseSplitSerializer(many=True, read_only=True)

    # Write-only input: shape depends on split_type (see class docstring
    # in split_service.py for what each function expects).
    #   equal:      [{"member_id": 7}, {"member_id": 8}]
    #   unequal:    [{"member_id": 7, "amount": "400.00"}, ...]
    #   percentage: [{"member_id": 7, "percentage": "25"}, ...]
    #   share:      [{"member_id": 7, "units": "2"}, ...]
    participants = serializers.ListField(
        child=serializers.DictField(), write_only=True
    )

    class Meta:
        model = Expense
        fields = [
            "id", "group", "description", "paid_by", "date",
            "currency", "amount", "exchange_rate_used", "amount_base_currency",
            "split_type", "notes", "source", "created_at",
            "splits", "participants",
        ]
        read_only_fields = ["exchange_rate_used", "amount_base_currency", "source", "created_at"]

    def validate_paid_by(self, paid_by):
        group = self.initial_data.get("group")
        if group and str(paid_by.group_id) != str(group):
            raise serializers.ValidationError("Payer must belong to the same group as the expense.")
        return paid_by

    @transaction.atomic
    def create(self, validated_data):
        participants_data = validated_data.pop("participants")
        split_type = validated_data["split_type"]
        amount = validated_data["amount"]
        currency = validated_data["currency"]

        # Currency conversion happens exactly once, here, at creation time -
        # the original amount/currency are never overwritten (Priya's
        # complaint from the assignment brief).
        if currency == Currency.USD:
            exchange_rate = USD_TO_INR_RATE
            amount_base_currency = (amount * exchange_rate).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
        else:
            exchange_rate = None
            amount_base_currency = amount

        expense = Expense(
            exchange_rate_used=exchange_rate,
            amount_base_currency=amount_base_currency,
            source=ExpenseSource.MANUAL,
            **validated_data,
        )
        # Triggers Expense.clean() - the membership-active-on-date check
        # from Module 3. full_clean() is NOT automatic on save(), so we
        # call it explicitly here, at the one place expenses get created
        # through the API. Django's ValidationError must be caught and
        # translated into DRF's ValidationError, or it propagates as an
        # unhandled 500 instead of a clean 400 - "never crash" applies
        # here just as much as it does to the CSV importer.
        try:
            expense.full_clean()
        except DjangoValidationError as e:
            raise serializers.ValidationError(
                e.message_dict if hasattr(e, "message_dict") else e.messages
            )
        expense.save()

        shares = self._calculate_shares(split_type, amount_base_currency, participants_data)

        ExpenseSplit.objects.bulk_create([
            ExpenseSplit(expense=expense, member_id=member_id, share_amount=share_amount)
            for member_id, share_amount in shares.items()
        ])

        return expense

    def _calculate_shares(self, split_type, amount_base_currency, participants_data):
        try:
            if split_type == SplitType.EQUAL:
                member_ids = [p["member_id"] for p in participants_data]
                return calculate_equal_split(amount_base_currency, member_ids)

            if split_type == SplitType.UNEQUAL:
                amounts_by_member = {
                    p["member_id"]: Decimal(str(p["amount"])) for p in participants_data
                }
                return calculate_unequal_split(amount_base_currency, amounts_by_member)

            if split_type == SplitType.PERCENTAGE:
                pct_by_member = {
                    p["member_id"]: Decimal(str(p["percentage"])) for p in participants_data
                }
                return calculate_percentage_split(amount_base_currency, pct_by_member)

            if split_type == SplitType.SHARE:
                units_by_member = {
                    p["member_id"]: Decimal(str(p["units"])) for p in participants_data
                }
                return calculate_share_split(amount_base_currency, units_by_member)

        except SplitValidationError as e:
            # Translate our plain-Python service exception into DRF's
            # validation error format, so the API returns a proper 400
            # with a clear message instead of a 500.
            raise serializers.ValidationError({"participants": str(e)})

        raise serializers.ValidationError({"split_type": f"Unknown split type: {split_type}"})


class SettlementSerializer(serializers.ModelSerializer):
    paid_by_username = serializers.CharField(source="paid_by.user.username", read_only=True)
    paid_to_username = serializers.CharField(source="paid_to.user.username", read_only=True)

    class Meta:
        model = Settlement
        fields = [
            "id", "group", "paid_by", "paid_by_username", "paid_to", "paid_to_username",
            "amount", "currency", "date", "notes", "source", "created_at",
        ]
        read_only_fields = ["source", "created_at"]

    def validate(self, data):
        if data.get("paid_by") == data.get("paid_to"):
            raise serializers.ValidationError("A member cannot settle a debt with themselves.")
        return data

    def create(self, validated_data):
        settlement = Settlement(source=ExpenseSource.MANUAL, **validated_data)
        try:
            settlement.full_clean()
        except DjangoValidationError as e:
            raise serializers.ValidationError(
                e.message_dict if hasattr(e, "message_dict") else e.messages
            )
        settlement.save()
        return settlement