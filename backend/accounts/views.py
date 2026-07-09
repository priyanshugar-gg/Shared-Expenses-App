from rest_framework import generics, permissions
from .serializers import RegisterSerializer


class RegisterView(generics.CreateAPIView):
    """
    Public signup endpoint. AllowAny overrides the project-wide default
    of IsAuthenticated (set in settings.py) - this is the one deliberate,
    explicit exception, since you obviously can't require a JWT to create
    the account that JWT would belong to.
    """
    permission_classes = [permissions.AllowAny]
    serializer_class = RegisterSerializer