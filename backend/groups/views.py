from expenses.services.balance_service import calculate_group_balances, get_member_balance_trace, simplify_debts
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import Group, GroupMembership
from .serializers import GroupSerializer, GroupMembershipSerializer


class GroupViewSet(viewsets.ModelViewSet):
    """
    A user can only ever see/act on groups they are actually a member
    of - enforced by overriding get_queryset(), the standard DRF
    pattern for "scope data to the requesting user."
    """
    serializer_class = GroupSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Group.objects.filter(memberships__user=self.request.user).distinct()

    def perform_create(self, serializer):
        # The creator becomes both the group's owner AND its first member -
        # a group with zero members would be a meaningless state.
        group = serializer.save(created_by=self.request.user)
        GroupMembership.objects.create(
            group=group, user=self.request.user, joined_at=group.created_at.date()
        )

    @action(detail=True, methods=["post"], url_path="members")
    def add_member(self, request, pk=None):
        """
        POST /api/groups/{id}/members/  {"user_id": X, "joined_at": "2026-02-01"}
        Kept as an action on GroupViewSet (rather than a fully separate
        viewset) since membership only ever makes sense in the context
        of one specific group - there's no standalone "list all
        memberships across all groups" use case in this app.
        """
        group = self.get_object()
        serializer = GroupMembershipSerializer(
            data=request.data, context={"group": group}
        )
        serializer.is_valid(raise_exception=True)
        serializer.save(group=group)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["patch"], url_path="members/(?P<membership_id>[^/.]+)")
    def update_member(self, request, pk=None, membership_id=None):
        """
        PATCH /api/groups/{id}/members/{membership_id}/  {"left_at": "2026-03-31"}
        This is specifically how we record someone leaving the group -
        we never delete a GroupMembership row, since that would erase
        the historical fact that they were once active (and would
        orphan any Expense/ExpenseSplit rows still pointing at them,
        which are PROTECTed for exactly this reason).
        """
        group = self.get_object()
        membership = GroupMembership.objects.get(id=membership_id, group=group)
        serializer = GroupMembershipSerializer(
            membership, data=request.data, partial=True, context={"group": group}
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)
    
    @action(detail=True, methods=["get"], url_path="balances")
    def balances(self, request, pk=None):
        """
        GET /api/groups/{id}/balances/
        Returns each member's net balance plus the minimal set of
        settle-up transactions - this is the direct answer to Aisha's
        "one number per person, who pays whom."
        """
        group = self.get_object()
        raw_balances = calculate_group_balances(group)

        memberships = {m.id: m for m in group.memberships.select_related("user")}
        balances_by_member = [
            {
                "membership_id": membership_id,
                "username": memberships[membership_id].user.username,
                "net_balance": balance,
            }
            for membership_id, balance in raw_balances.items()
        ]

        transactions = simplify_debts(raw_balances)
        settle_up = [
            {
                "from_username": memberships[t["from_id"]].user.username,
                "to_username": memberships[t["to_id"]].user.username,
                "amount": t["amount"],
            }
            for t in transactions
        ]

        return Response({"balances": balances_by_member, "settle_up": settle_up})

    @action(detail=True, methods=["get"], url_path="balances/(?P<membership_id>[^/.]+)/trace")
    def balance_trace(self, request, pk=None, membership_id=None):
        """
        GET /api/groups/{id}/balances/{membership_id}/trace/
        Rohan's "show me exactly which expenses make that up" - the
        itemized version of one member's balance.
        """
        group = self.get_object()
        membership = GroupMembership.objects.get(id=membership_id, group=group)
        trace = get_member_balance_trace(group, membership)
        return Response(trace)