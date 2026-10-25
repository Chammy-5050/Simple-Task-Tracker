import uuid

from django.conf import settings
from django.db import models


class VerificationCode(models.Model):
    """A single-use 6-digit code emailed to a user. Only its hash is stored."""

    EMAIL_VERIFY = "email_verify"
    PASSWORD_RESET = "password_reset"
    PURPOSES = (
        (EMAIL_VERIFY, "Email verification"),
        (PASSWORD_RESET, "Password reset"),
    )

    code_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, db_column="code_id")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="verification_codes",
        db_column="user_id",
    )
    purpose = models.CharField(max_length=20, choices=PURPOSES)
    # The address the code was sent to, so a later email change cannot reuse it.
    email = models.EmailField(max_length=255)
    code_hash = models.CharField(max_length=128)
    expires_at = models.DateTimeField()
    attempts = models.PositiveSmallIntegerField(default=0)
    used_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "verification_codes"
        indexes = [  # noqa: RUF012
            models.Index(fields=["user", "purpose", "-created_at"], name="verification_user_purpose"),
        ]

    def __str__(self):
        return f"{self.get_purpose_display()} code for {self.email}"
