from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from rest_framework.exceptions import AuthenticationFailed, ValidationError
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


def register_user(*, username, password, password_confirm, email=""):
    """Create a normal user with a validated, hashed password."""
    if not isinstance(password, str) or not password:
        raise ValidationError({"password": ["A password is required."]})
    if not isinstance(password_confirm, str) or not password_confirm:
        raise ValidationError(
            {"password_confirm": ["Please confirm your password."]}
        )
    if password != password_confirm:
        raise ValidationError({"password_confirm": ["Passwords do not match."]})

    User = get_user_model()
    user = User(username=username, email=User.objects.normalize_email(email))
    user.is_staff = False
    user.is_superuser = False

    try:
        validate_password(password, user=user)
    except DjangoValidationError as exc:
        raise ValidationError({"password": exc.messages}) from exc

    user.set_password(password)
    try:
        user.full_clean(validate_unique=False)
    except DjangoValidationError as exc:
        raise ValidationError(exc.message_dict) from exc

    try:
        with transaction.atomic():
            user.save(force_insert=True)
    except IntegrityError as exc:
        if User.objects.filter(username=user.username).exists():
            raise ValidationError(
                {"username": ["A user with this username already exists."]}
            ) from exc
        raise

    return user
