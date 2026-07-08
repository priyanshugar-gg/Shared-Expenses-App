from django.conf import settings
from django.db import models


class Group(models.Model):
    """
    A shared-expenses group (e.g. a flat/household).
    created_by uses PROTECT so we can't silently lose track of who
    owns a group if that user account is ever deleted — deletion
    would have to be a deliberate, explicit action instead.
    """
    name = models.CharField(max_length=100)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_groups",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class GroupMembership(models.Model):
    """
    Links a User to a Group for a specific time window.

    This table exists specifically to solve the "Sam moved in mid-April,
    Meera moved out end of March" problem from the assignment: membership
    is not a fixed fact, it's a time-bounded one. Any code that decides
    "who should this expense be split between" must check membership
    against the expense's date, not just group membership in general.

    left_at = None means the member is still active.
    """
    group = models.ForeignKey(
        Group,
        on_delete=models.CASCADE,
        related_name="memberships",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="group_memberships",
    )
    joined_at = models.DateField()
    left_at = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ["joined_at"]

    def __str__(self):
        status = "active" if self.left_at is None else f"left {self.left_at}"
        return f"{self.user.username} in {self.group.name} ({status})"

    def is_active_on(self, on_date):
        """
        True if this membership covers the given date.
        Used everywhere we need to validate "was this person actually
        part of the group when this expense happened" — e.g. rejecting
        Meera from an April expense split, or excluding Sam from March
        expenses.
        """
        if on_date < self.joined_at:
            return False
        if self.left_at is not None and on_date > self.left_at:
            return False
        return True