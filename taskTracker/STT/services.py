from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from django.forms import ImageField
from rest_framework.exceptions import AuthenticationFailed, NotAuthenticated, ValidationError
from rest_framework_simplejwt.tokens import RefreshToken

from .models import Projects


def login_user(*, request, email, password):
    """Authenticate an active user and return their JWT access/refresh pair."""
    email = get_user_model().objects.normalize_email(email)
    user = authenticate(request=request, email=email, password=password)

    if user is None or not user.is_active:
        raise AuthenticationFailed("Invalid email or password.")

    refresh = RefreshToken.for_user(user)

    return {
        "access": str(refresh.access_token),
        "refresh": str(refresh),
    }


def register_user(
    *, email, full_name, phone_no, password, password_confirm, profile_picture=None
):
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
    user = User(
        email=User.objects.normalize_email(email),
        full_name=full_name,
        phone_no=phone_no,
    )
    user.is_superuser = False
    user.is_staff = False

    try:
        validate_password(password, user=user)
    except DjangoValidationError as exc:
        raise ValidationError({"password": exc.messages}) from exc

    if profile_picture is not None:
        try:
            user.profile_picture = ImageField().clean(profile_picture)
        except DjangoValidationError as exc:
            raise ValidationError({"profile_picture": exc.messages}) from exc

    user.set_password(password)
    try:
        user.full_clean(validate_unique=False)
    except DjangoValidationError as exc:
        raise ValidationError(exc.message_dict) from exc

    try:
        with transaction.atomic():
            user.save(force_insert=True)
    except IntegrityError as exc:
        if User.objects.filter(email=user.email).exists():
            raise ValidationError(
                {"email": ["A user with this email already exists."]}
            ) from exc
        raise

    return user


def get_projects(*, user):
    """Admins see all projects; normal users see only projects they own."""
    if not user.is_authenticated or not user.is_active:
        raise NotAuthenticated()

    projects = Projects.objects.all()
    if not user.is_superuser:
        projects = projects.filter(user_id=user.pk)

    return projects.order_by("-created_at", "project_id")
