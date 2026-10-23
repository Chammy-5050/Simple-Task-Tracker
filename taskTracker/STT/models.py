import logging
import uuid

from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.core.files.storage import default_storage
from django.db import models

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
        return self.role_name or str(self.id)

    def save(self, *args, **kwargs):
        previous = None
        if self.pk:
            previous = Roles.objects.filter(pk=self.pk).values(
                "grants_staff_access",
                "grants_superuser_access",
            ).first()

        super().save(*args, **kwargs)

        if not previous:
            return

        flags_changed = (
            bool(previous.get("grants_staff_access")) != bool(self.grants_staff_access)
            or bool(previous.get("grants_superuser_access")) != bool(self.grants_superuser_access)
        )
        if not flags_changed:
            return

        Users.objects.filter(role_id=self.pk).update(
            is_superuser=bool(self.grants_superuser_access),
        )
        if not bool(self.grants_staff_access or self.grants_superuser_access):
            Users.objects.filter(role_id=self.pk).update(is_staff=False)

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
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")

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
    profile_picture = models.FileField(
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
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "users"

    def save(self, *args, **kwargs):
        old_photo_name = None
        if self.pk:
            try:
                previous = Users.objects.only("profile_photo").get(pk=self.pk)
                previous_name = previous.profile_photo.name if previous.profile_photo else None
                current_name = self.profile_photo.name if self.profile_photo else None
                if previous_name and previous_name != current_name:
                    old_photo_name = previous_name
            except Users.DoesNotExist:
                old_photo_name = None

        if self.role_id:
            if getattr(self, "role", None) and self.role.pk == self.role_id:
                role = self.role
            else:
                role = Roles.objects.only(
                    "grants_staff_access",
                    "grants_superuser_access",
                ).filter(pk=self.role_id).first()
            if role:
                self.is_superuser = bool(role.grants_superuser_access)
                if not bool(role.grants_staff_access or role.grants_superuser_access):
                    self.is_staff = False

        super().save(*args, **kwargs)

        if old_photo_name:
            storage = (
                self.profile_photo.storage 
                if self.profile_photo 
                else default_storage
            )
            try:
                storage.delete(old_photo_name)
            except Exception:
                logger.exception(
                    "Failed to delete old profile photo: %s",
                    old_photo_name,
                )

    def has_perm(self, perm, obj=None):
        return bool(self.is_superuser)

    def has_module_perms(self, app_label):
        return bool(self.is_superuser)

    def __str__(self):
        return self.email or str(self.id)

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
    project_picture = models.FileField(
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
        max_lenth=20,
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
                    status__in=TASK_STATUS
                ),
                name="task_status_valid"
            )
        ]