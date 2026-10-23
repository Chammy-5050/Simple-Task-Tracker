from django.test import TestCase
from rest_framework.exceptions import ValidationError

from .services import login_user, register_user


class RegistrationPasswordTests(TestCase):
    def register(self, password, confirmation):
        return register_user(
            username="new_member",
            password=password,
            password_confirm=confirmation,
        )

    def test_each_password_rule_is_enforced(self):
        for password in (
            "Ab3!xy",       # Too short.
            "abcdefg3!",    # No uppercase letter.
            "ABCDEFG3!",    # No lowercase letter.
            "Abcdefgh!",    # No number.
            "Abcdefg39",    # No special character.
            "Abcdef39 ",    # Whitespace is not a special character.
        ):
            with self.subTest(password=password):
                with self.assertRaises(ValidationError) as caught:
                    self.register(password, password)
                self.assertIn("password", caught.exception.detail)
        self.assertFalse(self.user_model().objects.exists())

    def test_confirmation_is_required_and_must_match_exactly(self):
        for confirmation in (None, "", "Different39!", "Ab3!xyZ9 "):
            with self.subTest(confirmation=confirmation):
                with self.assertRaises(ValidationError) as caught:
                    self.register("Ab3!xyZ9", confirmation)
                self.assertIn("password_confirm", caught.exception.detail)
        self.assertFalse(self.user_model().objects.exists())

    def test_empty_password_is_rejected(self):
        with self.assertRaises(ValidationError) as caught:
            self.register("", "")
        self.assertIn("password", caught.exception.detail)

    def test_eight_character_password_is_hashed_and_confirmation_not_saved(self):
        user = self.register("Ab3!xyZ9", "Ab3!xyZ9")
        user.refresh_from_db()
        self.assertTrue(user.check_password("Ab3!xyZ9"))
        self.assertNotEqual(user.password, "Ab3!xyZ9")
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertFalse(hasattr(user, "password_confirm"))

    def test_login_does_not_reapply_registration_password_rules(self):
        self.user_model().objects.create_user(
            username="existing_member", password="legacy-password"
        )
        tokens = login_user(
            request=None, username="existing_member", password="legacy-password"
        )
        self.assertIn("access", tokens)

    @staticmethod
    def user_model():
        from django.contrib.auth import get_user_model

        return get_user_model()
