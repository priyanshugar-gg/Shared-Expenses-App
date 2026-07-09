from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers


class RegisterSerializer(serializers.ModelSerializer):
    """
    Handles new user signup. Password validation reuses Django's
    built-in validators (the same ones referenced in settings.py's
    AUTH_PASSWORD_VALIDATORS) so signup enforces the same rules as
    the rest of the framework, rather than us re-inventing password
    strength rules here.
    """
    password = serializers.CharField(write_only=True, validators=[validate_password])

    class Meta:
        model = User
        fields = ["id", "username", "email", "password"]

    def create(self, validated_data):
        # create_user (not create) ensures the password is hashed,
        # never stored in plain text.
        return User.objects.create_user(
            username=validated_data["username"],
            email=validated_data.get("email", ""),
            password=validated_data["password"],
        )