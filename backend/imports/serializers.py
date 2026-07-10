from rest_framework import serializers

from .models import ImportBatch, ImportRow


class ImportRowSerializer(serializers.ModelSerializer):
    class Meta:
        model = ImportRow
        fields = [
            "id", "row_number", "raw_data", "resolved_data", "anomalies",
            "proposed_action", "resolution", "resolution_notes",
            "resulting_expense", "resulting_settlement",
        ]
        # raw_data is NEVER writable through the API - it's the permanent
        # record of what the source file actually said. Only resolution
        # (the human's decision) and resolution_notes are meant to be
        # set by a client; resolved_data can be edited to supply a
        # correction (e.g. a missing payer) alongside approval.
        read_only_fields = ["row_number", "raw_data", "anomalies", "proposed_action",
                             "resulting_expense", "resulting_settlement"]


class ImportBatchSerializer(serializers.ModelSerializer):
    rows = ImportRowSerializer(many=True, read_only=True)
    uploaded_by_username = serializers.CharField(source="uploaded_by.username", read_only=True)

    class Meta:
        model = ImportBatch
        fields = [
            "id", "group", "file_name", "uploaded_by", "uploaded_by_username",
            "uploaded_at", "status", "total_rows", "rows",
        ]
        read_only_fields = ["uploaded_by", "uploaded_at", "status", "total_rows"]