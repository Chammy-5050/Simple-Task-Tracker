from django.contrib.auth import authenticate
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.tokens import RefreshToken


def login_user(*, request, username, password):
    """Authenticate an active user and return their JWT access/refresh pair."""
    user = authenticate(request=request, username=username, password=password)

    if user is None or not user.is_active:
        raise AuthenticationFailed("Invalid username or password.")

    refresh = RefreshToken.for_user(user)

    return {
        "access": str(refresh.access_token),
        "refresh": str(refresh),
    }
