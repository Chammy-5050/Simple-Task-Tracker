"""Email delivery for verification codes and account notices.

Codes are sent by email only. Messages are rendered inside the caller's
transaction but handed to the mail server after it commits, on a background
thread, so a slow or failing SMTP server never blocks or breaks a request.
Delivery failures are logged server-side and never reported to the client.
"""

import logging
import secrets
import threading
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import check_password, make_password
from django.core.mail import EmailMultiAlternatives
from django.db import transaction
from django.template.loader import render_to_string
from django.utils import timezone

from .models import VerificationCode

logger = logging.getLogger(__name__)

CODE_LENGTH = 6
CODE_TTL = timedelta(minutes=10)
MAX_ATTEMPTS = 5
RESEND_COOLDOWN = timedelta(seconds=45)

_CODE_EMAILS = {
    VerificationCode.EMAIL_VERIFY: {
        "subject": "Verify your email for Task Tracker",
        "heading": "Verify your email",
        "intro": "Use this code to finish creating your Task Tracker account.",
    },
    VerificationCode.PASSWORD_RESET: {
        "subject": "Your Task Tracker password reset code",
        "heading": "Reset your password",
        "intro": "Use this code to choose a new password for your Task Tracker account.",
    },
}


def generate_code():
    return f"{secrets.randbelow(10 ** CODE_LENGTH):0{CODE_LENGTH}d}"


def _deliver(message):
    try:
        message.send()
    except Exception:
        # Never include the message body: it may contain a code.
        logger.exception("Failed to send email %r to %s", message.subject, ", ".join(message.to))


def _dispatch(message):
    if settings.NOTIFICATIONS_ASYNC:
        threading.Thread(target=_deliver, args=(message,), name="email-sender", daemon=True).start()
    else:
        _deliver(message)


def _send(*, to, subject, template, context):
    context = {
        "app_name": "Task Tracker",
        "frontend_url": settings.FRONTEND_URL,
        "logo_url": f"{settings.EMAIL_ASSET_BASE_URL}{settings.STATIC_URL}notifications/logo.png",
        "subject": subject,
        **context,
    }
    message = EmailMultiAlternatives(
        subject=subject,
        body=render_to_string(f"notifications/email/{template}.txt", context),
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[to],
    )
    message.attach_alternative(render_to_string(f"notifications/email/{template}.html", context), "text/html")
    transaction.on_commit(lambda: _dispatch(message))


def send_code(user, purpose):
    """Issue a fresh code for `purpose` and email it to the user.

    Any earlier unused code for the same purpose stops working. Returns False
    without sending anything while the previous code is inside the resend
    cooldown, so callers can answer identically either way.
    """
    now = timezone.now()
    with transaction.atomic():
        # Serialise sends per user so two quick requests cannot both pass the cooldown.
        get_user_model().objects.select_for_update().filter(pk=user.pk).exists()
        codes = VerificationCode.objects.filter(user=user, purpose=purpose)
        latest = codes.order_by("-created_at").only("created_at").first()
        if latest and now - latest.created_at < RESEND_COOLDOWN:
            return False
        codes.filter(used_at__isnull=True, expires_at__gt=now).update(expires_at=now)
        code = generate_code()
        VerificationCode.objects.create(
            user=user, purpose=purpose, email=user.email,
            code_hash=make_password(code), expires_at=now + CODE_TTL,
        )
        _send(
            to=user.email,
            template="code",
            context={
                **_CODE_EMAILS[purpose],
                "code": code,
                "full_name": user.full_name,
                "expires_minutes": int(CODE_TTL.total_seconds() // 60),
            },
            subject=_CODE_EMAILS[purpose]["subject"],
        )
    return True


def verify_code(*, user, purpose, code):
    """Consume the user's current code when `code` matches it.

    Returns the used VerificationCode, or None when there is no live code, the
    attempt limit is reached, or the guess is wrong. Wrong guesses are counted.
    """
    now = timezone.now()
    with transaction.atomic():
        current = (
            VerificationCode.objects.select_for_update()
            .filter(
                user=user, purpose=purpose, email__iexact=user.email,
                used_at__isnull=True, expires_at__gt=now,
            )
            .order_by("-created_at")
            .first()
        )
        if current is None or current.attempts >= MAX_ATTEMPTS:
            return None
        if not (isinstance(code, str) and check_password(code, current.code_hash)):
            current.attempts += 1
            current.save(update_fields=["attempts"])
            return None
        current.used_at = now
        current.save(update_fields=["used_at"])
        return current


def burn_hash_time(code):
    """Spend the same hashing time as a real check, for unknown accounts."""
    check_password(str(code), make_password(None))


def send_welcome_email(user):
    _send(
        to=user.email,
        subject="Welcome to Task Tracker",
        template="welcome",
        context={"full_name": user.full_name},
    )


def send_password_changed_email(user):
    _send(
        to=user.email,
        subject="Your Task Tracker password was changed",
        template="password_changed",
        context={"full_name": user.full_name, "changed_at": timezone.localtime()},
    )
