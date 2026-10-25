import re
from datetime import timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from notifications.models import VerificationCode

PASSWORD = "Valid-Password-927!"
NEW_PASSWORD = "Fresh-Password-531?"


def code_from(message):
    return re.search(r"\b(\d{6})\b", message.body).group(1)


@override_settings(ROOT_URLCONF="taskTracker.urls", NOTIFICATIONS_ASYNC=False)
class EmailFlowTestCase(TestCase):
    def setUp(self):
        cache.clear()
        self.api = APIClient()

    def post(self, path, data, **extra):
        # Emails go out after commit; run those callbacks inside the test transaction.
        with self.captureOnCommitCallbacks(execute=True):
            return self.api.post(f"/api/{path}", data, format="json", **extra)

    def register(self, email="new@example.com"):
        return self.post("auth/register/", {
            "email": email, "full_name": "New Member", "phone_no": "+255700000000",
            "password": PASSWORD, "password_confirm": PASSWORD,
        })

    def login(self, email="new@example.com", password=PASSWORD):
        return self.post("auth/login/", {"email": email, "password": password})

    def age_codes(self, seconds):
        VerificationCode.objects.update(created_at=timezone.now() - timedelta(seconds=seconds))


class EmailVerificationTests(EmailFlowTestCase):
    def test_registration_emails_a_hashed_code_and_blocks_sign_in_until_verified(self):
        response = self.register()
        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.data["email_verification_required"])
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.to, ["new@example.com"])
        code = code_from(message)
        self.assertIn(code, message.alternatives[0][0])
        stored = VerificationCode.objects.get()
        self.assertNotIn(code, stored.code_hash)
        self.assertEqual(stored.purpose, VerificationCode.EMAIL_VERIFY)
        self.assertAlmostEqual(stored.expires_at, timezone.now() + timedelta(minutes=10), delta=timedelta(seconds=5))

        blocked = self.login()
        self.assertEqual(blocked.status_code, 403)
        self.assertEqual(blocked.data["code"], "email_not_verified")
        # Still inside the resend cooldown, so no second email yet.
        self.assertEqual(len(mail.outbox), 1)

        self.assertEqual(self.post("auth/verify-email/", {"email": "new@example.com", "code": code}).status_code, 200)
        self.assertTrue(get_user_model().objects.get(email="new@example.com").email_verified)
        self.assertEqual(mail.outbox[-1].subject, "Welcome to Task Tracker")
        self.assertEqual(self.login().status_code, 200)

    def test_wrong_password_never_reveals_verification_state(self):
        self.register()
        self.assertEqual(self.login(password="Wrong-Password-1!").status_code, 401)

    def test_code_locks_after_five_wrong_guesses(self):
        self.register()
        code = code_from(mail.outbox[0])
        wrong = "000000" if code != "000000" else "111111"
        for _ in range(5):
            response = self.post("auth/verify-email/", {"email": "new@example.com", "code": wrong})
            self.assertEqual(response.status_code, 400)
        self.assertEqual(self.post("auth/verify-email/", {"email": "new@example.com", "code": code}).status_code, 400)
        self.assertEqual(VerificationCode.objects.get().attempts, 5)

    def test_expired_code_is_rejected(self):
        self.register()
        VerificationCode.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
        response = self.post("auth/verify-email/", {"email": "new@example.com", "code": code_from(mail.outbox[0])})
        self.assertEqual(response.status_code, 400)
        self.assertIn("code", response.data)

    def test_resend_respects_cooldown_and_replaces_the_previous_code(self):
        self.register()
        first = code_from(mail.outbox[0])
        resend = {"email": "new@example.com", "purpose": "email_verify"}
        response = self.post("auth/resend-code/", resend)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["resend_in"], 45)
        self.assertEqual(len(mail.outbox), 1)

        self.age_codes(46)
        self.post("auth/resend-code/", resend)
        self.assertEqual(len(mail.outbox), 2)
        second = code_from(mail.outbox[1])
        if first != second:
            self.assertEqual(self.post("auth/verify-email/", {"email": "new@example.com", "code": first}).status_code, 400)
        self.assertEqual(self.post("auth/verify-email/", {"email": "new@example.com", "code": second}).status_code, 200)

    def test_resend_answers_identically_for_unknown_and_verified_accounts(self):
        get_user_model().objects.create_user(email="known@example.com", password=PASSWORD)
        replies = [
            self.post("auth/resend-code/", {"email": email, "purpose": "email_verify"})
            for email in ("known@example.com", "nobody@example.com")
        ]
        self.assertEqual([r.status_code for r in replies], [200, 200])
        self.assertEqual(replies[0].data, replies[1].data)
        self.assertEqual(mail.outbox, [])

    def test_codes_must_be_six_digits(self):
        response = self.post("auth/verify-email/", {"email": "new@example.com", "code": "12ab"})
        self.assertEqual(response.status_code, 400)

    def test_staff_created_and_existing_accounts_are_already_verified(self):
        user = get_user_model().objects.create_user(email="made@example.com", password=PASSWORD)
        self.assertTrue(user.email_verified)
        self.assertEqual(self.login("made@example.com").status_code, 200)


class PasswordResetTests(EmailFlowTestCase):
    def setUp(self):
        super().setUp()
        self.user = get_user_model().objects.create_user(email="member@example.com", full_name="Member", password=PASSWORD)

    def reset_token(self):
        self.post("auth/password/forgot/", {"email": "member@example.com"})
        response = self.post("auth/password/verify-code/", {"email": "member@example.com", "code": code_from(mail.outbox[-1])})
        self.assertEqual(response.status_code, 200)
        return response.data["reset_token"]

    def test_forgot_password_never_reveals_whether_the_email_exists(self):
        known = self.post("auth/password/forgot/", {"email": "member@example.com"})
        unknown = self.post("auth/password/forgot/", {"email": "nobody@example.com"})
        self.assertEqual((known.status_code, unknown.status_code), (200, 200))
        self.assertEqual(known.data, unknown.data)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["member@example.com"])
        self.assertEqual(VerificationCode.objects.get().purpose, VerificationCode.PASSWORD_RESET)

    def test_unknown_email_and_wrong_code_fail_the_same_way(self):
        self.post("auth/password/forgot/", {"email": "member@example.com"})
        unknown = self.post("auth/password/verify-code/", {"email": "nobody@example.com", "code": "123456"})
        wrong = self.post("auth/password/verify-code/", {"email": "member@example.com", "code": "999999" if code_from(mail.outbox[0]) != "999999" else "888888"})
        self.assertEqual((unknown.status_code, wrong.status_code), (400, 400))
        self.assertEqual(unknown.data, wrong.data)

    def test_reset_signs_out_everywhere_and_the_token_is_single_use(self):
        tokens = self.login("member@example.com").data
        token = self.reset_token()
        response = self.post("auth/password/reset/", {"reset_token": token, "password": NEW_PASSWORD, "confirm_password": NEW_PASSWORD})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(mail.outbox[-1].subject, "Your Task Tracker password was changed")

        self.api.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
        self.assertEqual(self.api.get("/api/users/me/").status_code, 401)
        self.api.credentials()
        self.assertEqual(self.post("auth/refresh/", {"refresh": tokens["refresh"]}).status_code, 401)

        again = self.post("auth/password/reset/", {"reset_token": token, "password": "Another-Pass-77!", "confirm_password": "Another-Pass-77!"})
        self.assertEqual(again.status_code, 400)
        self.assertIn("reset_token", again.data)
        self.assertEqual(self.login("member@example.com", PASSWORD).status_code, 401)
        self.assertEqual(self.login("member@example.com", NEW_PASSWORD).status_code, 200)

    def test_reset_enforces_password_rules_and_confirmation(self):
        token = self.reset_token()
        weak = self.post("auth/password/reset/", {"reset_token": token, "password": "alllowercase", "confirm_password": "alllowercase"})
        self.assertEqual(weak.status_code, 400)
        self.assertIn("password", weak.data)
        mismatch = self.post("auth/password/reset/", {"reset_token": token, "password": NEW_PASSWORD, "confirm_password": PASSWORD})
        self.assertIn("confirm_password", mismatch.data)
        self.assertTrue(get_user_model().objects.get(pk=self.user.pk).check_password(PASSWORD))

    @override_settings(PASSWORD_RESET_TOKEN_MAX_AGE=-1)
    def test_expired_or_forged_reset_tokens_are_rejected(self):
        for token in (self.reset_token(), "forged-token"):
            response = self.post("auth/password/reset/", {"reset_token": token, "password": NEW_PASSWORD, "confirm_password": NEW_PASSWORD})
            self.assertEqual(response.status_code, 400)
            self.assertIn("reset_token", response.data)

    def test_reset_code_cannot_be_used_twice(self):
        self.post("auth/password/forgot/", {"email": "member@example.com"})
        payload = {"email": "member@example.com", "code": code_from(mail.outbox[-1])}
        self.assertEqual(self.post("auth/password/verify-code/", payload).status_code, 200)
        self.assertEqual(self.post("auth/password/verify-code/", payload).status_code, 400)

    def test_changing_password_in_settings_emails_and_revokes_other_sessions(self):
        tokens = self.login("member@example.com").data
        self.api.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
        response = self.post("users/me/password/", {"current_password": PASSWORD, "password": NEW_PASSWORD, "password_confirm": NEW_PASSWORD})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(mail.outbox[-1].subject, "Your Task Tracker password was changed")
        self.assertEqual(self.api.get("/api/users/me/").status_code, 401)


class ThrottleAndDeliveryTests(EmailFlowTestCase):
    def test_code_requests_are_limited_per_ip(self):
        statuses = [
            self.post("auth/password/forgot/", {"email": f"person{n}@example.com"}).status_code
            for n in range(6)
        ]
        self.assertEqual(statuses, [200] * 5 + [429])

    def test_code_requests_are_limited_per_address_across_ips(self):
        statuses = [
            self.post("auth/password/forgot/", {"email": "Target@Example.com"}, REMOTE_ADDR=f"10.0.0.{n}").status_code
            for n in range(6)
        ]
        self.assertEqual(statuses, [200] * 5 + [429])

    def test_forwarded_for_header_cannot_bypass_the_ip_limit(self):
        statuses = [
            self.post("auth/password/forgot/", {"email": f"p{n}@example.com"}, HTTP_X_FORWARDED_FOR=f"203.0.113.{n}").status_code
            for n in range(6)
        ]
        self.assertEqual(statuses[-1], 429)

    def test_delivery_failures_are_logged_not_returned(self):
        get_user_model().objects.create_user(email="member@example.com", password=PASSWORD)
        with mock.patch("django.core.mail.EmailMultiAlternatives.send", side_effect=OSError("SMTP down")):
            with self.assertLogs("notifications.services", level="ERROR") as logs:
                response = self.post("auth/password/forgot/", {"email": "member@example.com"})
        self.assertEqual(response.status_code, 200)
        self.assertNotRegex("\n".join(logs.output), r"\b\d{6}\b")
