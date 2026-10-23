import logging
import uuid

from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.core.files.storage import default_storage
from django.db import models
from django.db import transaction

TASK_STATUS = (
  ("pending", "Pending"),
  ("in_progress", "In progress"),
  ("done", "Done"),        
)

logger = logging.getLogger(__name__)

# Create your models here.

class Roles(models.Model):
    role_id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        db_column="role_id"
    )
    role_name = models.CharField(
        unique=True,
        max_length=255,
        db_column="role_name",
        blank=False,
        null=False,
    )
    description = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        db_column="description"
    )
    grant_superuser_access = models.BooleanField(default=False)

    class Meta:
        db_table="roles"

    def __str__(self):
        return self.role_name or str(self.pk)

    def save(self, *args, **kwargs):
        with transaction.atomic():
            super().save(*args, **kwargs)
            saved_role = Roles.objects.get(pk=self.pk)
            Users.objects.filter(role_id=self.pk).update(
                is_superuser=saved_role.grant_superuser_access,
            )

class UsersManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("Users must have an email address")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)

        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")
        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_active") is not True:
            raise ValueError("Superuser must have is_active=True.")
        role = extra_fields.get("role")
        if role is not None and not role.grant_superuser_access:
            raise ValueError("A superuser's role must grant superuser access.")

        return self.create_user(email, password, **extra_fields)
    
class Users(AbstractBaseUser):
    user_id = models.UUIDField(
        primary_key=True, 
        default=uuid.uuid4, 
        editable=False,
        db_column="user_id",
    )
    password = models.CharField(
        "password", 
        max_length=128, 
        db_column="password_hash"
    )
    full_name = models.CharField(
        max_length=255,
        blank=False,
        null=False,
        db_column="full_name"
    )
    email = models.EmailField(
        unique=True,
        max_length=255,
        blank=False,
        null=False,
        db_column="email"
    )
    phone_no = models.CharField(
        max_length=20,
        db_column="phone_no"
    )
    profile_picture = models.ImageField(
        upload_to="profile_photos/",
        blank=True,
        null=True,
        db_column="profile_picture"
    )
    is_superuser = models.BooleanField(
        default=False,
        verbose_name="Superuser Status",
        help_text="Gain superuser privileges without being assigned"
    )
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    role = models.ForeignKey(
        Roles,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        db_column="role_id",
        related_name="users",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = UsersManager()

    USERNAME_FIELD = "email"
    EMAIL_FIELD = "email"
    REQUIRED_FIELDS = ["full_name", "phone_no"]

    class Meta:
        db_table = "users"

    def save(self, *args, **kwargs):
        old_photo_name = None
        picture_is_saved = (
            kwargs.get("update_fields") is None
            or "profile_picture" in kwargs["update_fields"]
        )
        if self.pk and picture_is_saved:
            try:
                previous = Users.objects.only("profile_picture").get(pk=self.pk)
                previous_name = previous.profile_picture.name if previous.profile_picture else None
                current_name = self.profile_picture.name if self.profile_picture else None
                if previous_name and previous_name != current_name:
                    old_photo_name = previous_name
            except Users.DoesNotExist:
                old_photo_name = None

        if self.role_id:
            role = Roles.objects.only("grant_superuser_access").filter(pk=self.role_id).first()
            if role:
                self.is_superuser = bool(role.grant_superuser_access)
                if kwargs.get("update_fields") is not None:
                    kwargs["update_fields"] = set(kwargs["update_fields"]) | {"is_superuser"}

        super().save(*args, **kwargs)

        if old_photo_name:
            storage = (
                self.profile_picture.storage
                if self.profile_picture
                else default_storage
            )
            def delete_old_photo():
                try:
                    storage.delete(old_photo_name)
                except Exception:
                    logger.exception("Failed to delete old profile photo: %s", old_photo_name)

            transaction.on_commit(delete_old_photo)

    def has_perm(self, perm, obj=None):
        return bool(self.is_active and self.is_superuser)

    def has_module_perms(self, app_label):
        return bool(self.is_active and self.is_superuser)

    def __str__(self):
        return self.email or str(self.pk)

class Projects(models.Model):
    project_id = models.UUIDField(
        primary_key=True, 
        default=uuid.uuid4, 
        editable=False,
        db_column="project_id",
    )
    project_name = models.CharField(
        unique=True,
        max_length=255,
        blank=False,
        null=False,
        db_column="project_name",
    )
    project_picture = models.ImageField(
        upload_to="profile_photos/",
        blank=True,
        null=True,
        db_column="project_picture"
    )
    description = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        db_column="description"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    user_id=models.ForeignKey(
        Users,
        models.DO_NOTHING,
        blank=False,
        null=False,
        db_column="user_id"
    )

    class Meta:
        db_table="projects"


class Tasks(models.Model):
    task_id= models.UUIDField(
        primary_key=True, 
        default=uuid.uuid4, 
        editable=False,
        db_column="task_id",
    )
    task_name = models.CharField(
        unique=True,
        max_length=255,
        blank=False,
        null=False,
        db_column="task_name",
    )
    description = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        db_column="description"
    )
    status = models.CharField(
        max_length=20,
        blank=False,
        null=False,
        choices=TASK_STATUS,
        default="pending",
        db_column="status",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    project_id=models.ForeignKey(
        Projects,
        models.DO_NOTHING,
        blank=False,
        null=False,
        db_column="project_id"
    )

    class Meta:
        db_table="tasks"
        constraints = [  # noqa: RUF012
            models.CheckConstraint(
                condition=models.Q(
                    status__in=[value for value, label in TASK_STATUS]
                ),
                name="task_status_valid"
            )
        ]
