from django.shortcuts import get_object_or_404
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.response import Response

from groups.models import Group
from .models import ImportBatch, ImportRow, ImportBatchStatus, ProposedAction, RowResolution
from .serializers import ImportBatchSerializer, ImportRowSerializer
from .services.import_service import scan_csv, commit_batch


class ImportBatchViewSet(viewsets.ModelViewSet):
    """
    Scoped to import batches in groups the requesting user belongs to,
    same pattern as ExpenseViewSet/SettlementViewSet. create() is
    overridden - a batch isn't built from plain serializer fields, it's
    the result of running the actual scan pipeline (parser + all 15
    anomaly detectors) against an uploaded file.
    """
    serializer_class = ImportBatchSerializer
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_queryset(self):
        return ImportBatch.objects.filter(
            group__memberships__user=self.request.user
        ).distinct().prefetch_related("rows")

    def create(self, request, *args, **kwargs):
        group_id = request.data.get("group")
        uploaded_file = request.data.get("file")

        if not group_id or not uploaded_file:
            return Response(
                {"detail": "Both 'group' and 'file' are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        group = get_object_or_404(
            Group, id=group_id, memberships__user=request.user
        )

        batch = scan_csv(uploaded_file, uploaded_file.name, group, request.user)
        serializer = self.get_serializer(batch)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["patch"], url_path="rows/(?P<row_id>[^/.]+)")
    def update_row(self, request, pk=None, row_id=None):
        """
        PATCH /api/imports/{batch_id}/rows/{row_id}/
        Body: {"resolution": "approved"} or {"resolution": "rejected"}
        or {"resolution": "edited", "resolved_data": {...}, "resolution_notes": "..."}

        This is the literal mechanism behind Meera's "I want to approve
        anything the app deletes or changes" - nothing in a
        needs_manual_review row reaches commit_batch() without a
        PATCH like this setting resolution explicitly.
        """
        batch = self.get_object()
        row = get_object_or_404(ImportRow, id=row_id, batch=batch)

        if batch.status != ImportBatchStatus.PENDING_REVIEW:
            return Response(
                {"detail": f"Cannot modify rows on a batch with status '{batch.status}'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = ImportRowSerializer(row, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    @action(detail=True, methods=["post"], url_path="commit")
    @action(detail=True, methods=["post"], url_path="commit")
    def commit(self, request, pk=None):
        batch = self.get_object()
        try:
            commit_batch(batch)
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        # get_object() prefetch_related("rows") cached the rows BEFORE
        # commit_batch() updated them via separate queries - re-fetch
        # to serialize the actual post-commit state, not the stale
        # in-memory snapshot from before commit ran.
        batch.refresh_from_db()
        serializer = self.get_serializer(
            ImportBatch.objects.prefetch_related("rows").get(pk=batch.pk)
        )
        return Response(serializer.data)

    @action(detail=True, methods=["get"], url_path="report")
    def report(self, request, pk=None):
        """
        GET /api/imports/{batch_id}/report/
        The required "import report - listing every anomaly detected
        and the action taken" deliverable, as a real queryable
        endpoint rather than a static file.
        """
        batch = self.get_object()
        rows = batch.rows.all()

        anomaly_counts = {}
        for row in rows:
            for anomaly in row.anomalies:
                anomaly_counts[anomaly["type"]] = anomaly_counts.get(anomaly["type"], 0) + 1

        return Response({
            "batch_id": batch.id,
            "file_name": batch.file_name,
            "status": batch.status,
            "total_rows": batch.total_rows,
            "created_expenses": rows.filter(resulting_expense__isnull=False).count(),
            "created_settlements": rows.filter(resulting_settlement__isnull=False).count(),
            "skipped_as_duplicate": rows.filter(proposed_action=ProposedAction.SKIP).count(),
            "still_pending_review": rows.filter(resolution__isnull=True).count(),
            "rejected_by_user": rows.filter(resolution=RowResolution.REJECTED).count(),
            "anomaly_counts_by_type": anomaly_counts,
            "rows_with_anomalies": [
                {
                    "row_number": row.row_number,
                    "anomalies": row.anomalies,
                    "proposed_action": row.proposed_action,
                    "resolution": row.resolution,
                }
                for row in rows if row.anomalies
            ],
        })