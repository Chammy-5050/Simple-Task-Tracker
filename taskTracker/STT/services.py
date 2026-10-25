from django.conf import settings
from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core import signing
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from django.forms import ImageField
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.crypto import constant_time_compare
from rest_framework import status
from rest_framework.exceptions import APIException, AuthenticationFailed, NotAuthenticated, PermissionDenied, ValidationError
from rest_framework_simplejwt.tokens import RefreshToken

from notifications.models import VerificationCode
from notifications.services import (
    burn_hash_time, send_code, send_password_changed_email, send_welcome_email, verify_code,
)

from .models import Projects, Tasks

INVALID_CODE = "That code is incorrect or has expired. Check the latest email or request a new code."
INVALID_RESET_TOKEN = "This reset session has expired. Request a new code to try again."
RESET_TOKEN_SALT = "STT.password-reset"


class EmailNotVerified(APIException):
    status_code = status.HTTP_403_FORBIDDEN
    default_code = "email_not_verified"

    def __init__(self, email):
        super().__init__({
            "detail": "Verify your email to sign in. We sent a 6-digit code to your inbox.",
            "code": self.default_code,
            "email": email,
        })


def login_user(*, request, email, password):
    """Authenticate an active user and return their JWT access/refresh pair."""
    email = get_user_model().objects.normalize_email(email)
    user = authenticate(request=request, email=email, password=password)

    if user is None or not user.is_active:
        raise AuthenticationFailed("Invalid email or password.")
    if not user.email_verified:
        # Only reachable with the right password, so this reveals nothing new.
        send_code(user, VerificationCode.EMAIL_VERIFY)
        raise EmailNotVerified(user.email)

    refresh = RefreshToken.for_user(user)

    return {
        "access": str(refresh.access_token),
        "refresh": str(refresh),
    }


def register_user(*, email, full_name, phone_no, password, password_confirm):
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
    user.email_verified = False

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
        if User.objects.filter(email=user.email).exists():
            raise ValidationError(
                {"email": ["A user with this email already exists."]}
            ) from exc
        raise

    send_code(user, VerificationCode.EMAIL_VERIFY)
    return user


def _active_user(email):
    User = get_user_model()
    return User.objects.filter(email=User.objects.normalize_email(email), is_active=True).first()


def verify_email(*, email, code):
    """Mark the account verified when the emailed code matches, then welcome them."""
    user = _active_user(email)
    if user is None or user.email_verified:
        burn_hash_time(code)
        raise ValidationError({"code": [INVALID_CODE]})
    if verify_code(user=user, purpose=VerificationCode.EMAIL_VERIFY, code=code) is None:
        raise ValidationError({"code": [INVALID_CODE]})
    with transaction.atomic():
        user.email_verified = True
        user.save(update_fields=["email_verified", "updated_at"])
        send_welcome_email(user)
    return user


def resend_code(*, email, purpose):
    """Send a new code if the account can use one. Callers answer the same either way."""
    user = _active_user(email)
    if user is None:
        return
    if purpose == VerificationCode.EMAIL_VERIFY and user.email_verified:
        return
    send_code(user, purpose)


def request_password_reset(*, email):
    resend_code(email=email, purpose=VerificationCode.PASSWORD_RESET)


def verify_reset_code(*, email, code):
    """Exchange a valid reset code for a short-lived, single-use reset token.

    The token embeds a fingerprint of the current password hash, so it stops
    working as soon as the password changes (including by this reset).
    """
    user = _active_user(email)
    if user is None:
        burn_hash_time(code)
        raise ValidationError({"code": [INVALID_CODE]})
    used = verify_code(user=user, purpose=VerificationCode.PASSWORD_RESET, code=code)
    if used is None:
        raise ValidationError({"code": [INVALID_CODE]})
    return signing.dumps(
        {"u": str(user.pk), "c": str(used.pk), "p": user.get_session_auth_hash()},
        salt=RESET_TOKEN_SALT,
    )


def reset_password(*, reset_token, password, confirm_password):
    """Set a new password from a reset token and sign the account out everywhere."""
    try:
        data = signing.loads(reset_token, salt=RESET_TOKEN_SALT, max_age=settings.PASSWORD_RESET_TOKEN_MAX_AGE)
    except signing.BadSignature as exc:
        raise ValidationError({"reset_token": [INVALID_RESET_TOKEN]}) from exc
    User = get_user_model()
    user = User.objects.filter(pk=data.get("u"), is_active=True).first() if isinstance(data, dict) else None
    if user is None or not constant_time_compare(str(data.get("p")), user.get_session_auth_hash()):
        raise ValidationError({"reset_token": [INVALID_RESET_TOKEN]})
    if password != confirm_password:
        raise ValidationError({"confirm_password": ["Passwords do not match."]})
    try:
        validate_password(password, user=user)
    except DjangoValidationError as exc:
        raise ValidationError({"password": exc.messages}) from exc

    with transaction.atomic():
        user.set_password(password)
        # Receiving the code proved the user owns this address.
        user.email_verified = True
        user.save(update_fields=["password", "email_verified", "updated_at"])
        VerificationCode.objects.filter(
            user=user, purpose=VerificationCode.PASSWORD_RESET, used_at__isnull=True,
        ).update(expires_at=timezone.now())
        send_password_changed_email(user)
    return user


def get_projects(*, user):
    """Team superusers see all projects; members see only their own."""
    if user is None or not user.is_authenticated or not user.is_active:
        raise NotAuthenticated()

    projects = Projects.objects.select_related("user_id")
    if not user.is_superuser:
        projects = projects.filter(user_id=user.pk)

    return projects.order_by("-created_at", "project_id")


def create_project(*, user, project_name, description=""):
    """Create a project owned by the authenticated user."""
    if user is None or not user.is_authenticated or not user.is_active:
        raise NotAuthenticated()
    if user.is_superuser:
        raise PermissionDenied("Administrators can view projects but cannot create them.")

    project = Projects(
        project_name=project_name,
        description=description,
        user_id=user,
    )
    try:
        project.full_clean(validate_unique=False, validate_constraints=False)
    except DjangoValidationError as exc:
        raise ValidationError(exc.message_dict) from exc

    try:
        with transaction.atomic():
            project.save(force_insert=True)
    except IntegrityError as exc:
        if Projects.objects.filter(user_id=user, project_name=project.project_name).exists():
            raise ValidationError(
                {"project_name": ["A project with this name already exists."]}
            ) from exc
        raise

    return project


def update_profile_picture(*, user, profile_picture):
    """Validate an image and replace only the authenticated user's picture."""
    if user is None or not user.is_authenticated or not user.is_active:
        raise NotAuthenticated()

    try:
        picture = ImageField().clean(profile_picture)
    except DjangoValidationError as exc:
        raise ValidationError({"profile_picture": exc.messages}) from exc

    User = get_user_model()
    with transaction.atomic():
        try:
            account = User.objects.select_for_update().get(pk=user.pk, is_active=True)
        except User.DoesNotExist as exc:
            raise NotAuthenticated() from exc
        account.profile_picture = picture
        account.save(update_fields=["profile_picture", "updated_at"])

    return account


def get_project_tasks(*, user, project_id):
    """List tasks only after verifying access to the containing project."""
    project = get_object_or_404(get_projects(user=user), pk=project_id)
    return Tasks.objects.filter(project_id=project).select_related("project_id__user_id").order_by("created_at", "task_id")


def create_project_task(
    *, user, project_id, task_name, description="", status="pending", due_date=None
):
    """Create a task in the authorized project selected by the URL."""
    project = get_object_or_404(get_projects(user=user), pk=project_id)
    if project.user_id_id != user.pk:
        raise PermissionDenied("Other users' projects are read-only.")
    task = Tasks(
        project_id=project,
        task_name=task_name,
        description=description,
        status=status,
        due_date=due_date,
    )
    try:
        task.full_clean(validate_unique=False, validate_constraints=False)
    except DjangoValidationError as exc:
        raise ValidationError(exc.message_dict) from exc

    try:
        with transaction.atomic():
            task.save(force_insert=True)
    except IntegrityError as exc:
        if Tasks.objects.filter(project_id=project, task_name=task.task_name).exists():
            raise ValidationError(
                {"task_name": ["A task with this name already exists in this project."]}
            ) from exc
        raise

    return task


def _owned_project(*, user, project_id, action):
    """Return a visible project, refusing changes by anyone but its owner."""
    project = get_object_or_404(get_projects(user=user), pk=project_id)
    if project.user_id_id != user.pk:
        raise PermissionDenied(f"Only the project owner can {action}.")
    return project


def update_project(*, user, project_id, changes):
    project = _owned_project(user=user, project_id=project_id, action="update this project")
    for field in ("project_name", "description"):
        if field in changes:
            setattr(project, field, changes[field])
    try:
        project.full_clean(validate_unique=False, validate_constraints=False)
    except DjangoValidationError as exc:
        raise ValidationError(exc.message_dict) from exc
    duplicate = Projects.objects.filter(user_id=user, project_name=project.project_name).exclude(pk=project.pk)
    if duplicate.exists():
        raise ValidationError({"project_name": ["A project with this name already exists."]})
    project.save()
    return project


def delete_project(*, user, project_id):
    """Delete an owned project together with all of its tasks."""
    project = _owned_project(user=user, project_id=project_id, action="delete this project")
    with transaction.atomic():
        Tasks.objects.filter(project_id=project).delete()
        project.delete()


def update_task(*, user, project_id, task_id, changes):
    project = _owned_project(user=user, project_id=project_id, action="update this task")
    task = get_object_or_404(Tasks, pk=task_id, project_id=project)
    for field in ("task_name", "description", "status", "due_date"):
        if field in changes:
            setattr(task, field, changes[field])
    try:
        task.full_clean(validate_unique=False, validate_constraints=False)
    except DjangoValidationError as exc:
        raise ValidationError(exc.message_dict) from exc
    duplicate = Tasks.objects.filter(project_id=project, task_name=task.task_name).exclude(pk=task.pk)
    if duplicate.exists():
        raise ValidationError({"task_name": ["A task with this name already exists in this project."]})
    with transaction.atomic():
        task.save()
    return task


def delete_task(*, user, project_id, task_id):
    project = _owned_project(user=user, project_id=project_id, action="delete this task")
    get_object_or_404(Tasks, pk=task_id, project_id=project).delete()


def update_user_profile(*, user, changes):
    if user is None or not user.is_authenticated or not user.is_active:
        raise NotAuthenticated()
    for field in ("full_name", "email", "phone_no"):
        if field in changes:
            setattr(user, field, changes[field])
    user.email = get_user_model().objects.normalize_email(user.email)
    try:
        user.full_clean()
    except DjangoValidationError as exc:
        raise ValidationError(exc.message_dict) from exc
    user.save(update_fields=["full_name", "email", "phone_no", "updated_at"])
    return user


def change_user_password(*, user, current_password, password, password_confirm):
    if not user.check_password(current_password):
        raise ValidationError({"current_password": ["Current password is incorrect."]})
    if password != password_confirm:
        raise ValidationError({"password_confirm": ["Passwords do not match."]})
    try:
        validate_password(password, user=user)
    except DjangoValidationError as exc:
        raise ValidationError({"password": exc.messages}) from exc
    with transaction.atomic():
        user.set_password(password)
        user.save(update_fields=["password", "updated_at"])
        send_password_changed_email(user)
