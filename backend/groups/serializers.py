from django.contrib.auth.models import User
from rest_framework import serializers

from .models import Group, GroupMembership


class UserSummarySerializer(serializers.ModelSerializer):
    """
    Minimal user representation for nesting inside other serializers -
    we deliberately never expose the full User object (which could
    leak email, etc.) in places like "list of group members."
    """
    class Meta:
        model = User
        fields = ["id", "username"]


class GroupMembershipSerializer(serializers.ModelSerializer):
    user = UserSummarySerializer(read_only=True)
    user_id = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(), source="user", write_only=True
    )

    class Meta:
        model = GroupMembership
        fields = ["id", "group", "user", "user_id", "joined_at", "left_at"]
        read_only_fields = ["group"]

    def validate(self, data):
        """
        Enforce "at most one currently-active membership per user per
        group" at the application level (recall from Module 2: we
        deliberately chose this over a database partial-unique index,
        since app-level validation is proportional to this project's
        actual risk).
        """
        group = self.context["group"]
        user = data.get("user")
        left_at = data.get("left_at")

        if left_at is None and user is not None:
            existing_active = GroupMembership.objects.filter(
                group=group, user=user, left_at__isnull=True
            )
            if self.instance:
                existing_active = existing_active.exclude(id=self.instance.id)
            if existing_active.exists():
                raise serializers.ValidationError(
                    f"{user.username} already has an active membership in this group."
                )
        return data


class GroupSerializer(serializers.ModelSerializer):
    created_by = UserSummarySerializer(read_only=True)
    memberships = GroupMembershipSerializer(many=True, read_only=True)

    class Meta:
        model = Group
        fields = ["id", "name", "created_by", "created_at", "memberships"]
        read_only_fields = ["created_by"]