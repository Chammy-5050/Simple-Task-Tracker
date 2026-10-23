from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from django.forms import ImageField
from django.shortcuts import get_object_or_404
from rest_framework.exceptions import AuthenticationFailed, NotAuthenticated, PermissionDenied, ValidationError
from rest_framework_simplejwt.tokens import RefreshToken

from .models import Projects, Tasks


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

    project = Projects(
        project_name=project_name,
        description=description,
        user_id=user,
    )
    try:
        project.full_clean(validate_unique=False)
    except DjangoValidationError as exc:
        raise ValidationError(exc.message_dict) from exc

    try:
        with transaction.atomic():
            project.save(force_insert=True)
    except IntegrityError as exc:
        if Projects.objects.filter(project_name=project.project_name).exists():
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
        task.full_clean(validate_unique=False)
    except DjangoValidationError as exc:
        raise ValidationError(exc.message_dict) from exc

    try:
        with transaction.atomic():
            task.save(force_insert=True)
    except IntegrityError as exc:
        if Tasks.objects.filter(task_name=task.task_name).exists():
            raise ValidationError(
                {"task_name": ["A task with this name already exists."]}
            ) from exc
        raise

    return task


def update_task(*, user, project_id, task_id, changes):
    project = get_object_or_404(get_projects(user=user), pk=project_id)
    if project.user_id_id != user.pk:
        raise PermissionDenied("Only the task owner can update this task.")
    task = get_object_or_404(Tasks, pk=task_id, project_id=project)
    for field in ("task_name", "description", "status", "due_date"):
        if field in changes:
            setattr(task, field, changes[field])
    try:
        task.full_clean()
    except DjangoValidationError as exc:
        raise ValidationError(exc.message_dict) from exc
    with transaction.atomic():
        task.save()
    return task


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
    user.set_password(password)
    user.save(update_fields=["password", "updated_at"])
