from rest_framework import viewsets, permissions

from .models import Expense, Settlement
from .serializers import ExpenseSerializer, SettlementSerializer


class ExpenseViewSet(viewsets.ModelViewSet):
    """
    Scoped to expenses in groups the requesting user belongs to.
    Supports ?group=<id> to filter to one specific group, which is
    how the frontend will always call this in practice (an expense
    list is always viewed within one group's context).
    """
    serializer_class = ExpenseSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        queryset = Expense.objects.filter(
            group__memberships__user=self.request.user
        ).distinct()
        group_id = self.request.query_params.get("group")
        if group_id:
            queryset = queryset.filter(group_id=group_id)
        return queryset.prefetch_related("splits")


class SettlementViewSet(viewsets.ModelViewSet):
    serializer_class = SettlementSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        queryset = Settlement.objects.filter(
            group__memberships__user=self.request.user
        ).distinct()
        group_id = self.request.query_params.get("group")
        if group_id:
            queryset = queryset.filter(group_id=group_id)
        return queryset