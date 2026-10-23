from django.contrib.auth import get_user_model
from django.contrib import admin
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.urls import path
from rest_framework.exceptions import AuthenticationFailed, ValidationError
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.test import APIRequestFactory

from .models import Projects, Roles, Tasks
from .services import get_projects, login_user, register_user

urlpatterns = [path("admin/", admin.site.urls)]


class RegistrationPasswordTests(TestCase):
    def register(self, password, confirmation):
        return register_user(
            email="new_member@example.com",
            full_name="New Member",
            phone_no="+255700000000",
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
        self.assertFalse(user.is_superuser)
        self.assertFalse(user.is_staff)
        self.assertFalse(hasattr(user, "password_confirm"))

    def test_login_does_not_reapply_registration_password_rules(self):
        self.user_model().objects.create_user(
            email="existing_member@example.com", password="legacy-password",
            full_name="Existing Member", phone_no="+255700000000",
        )
        tokens = login_user(
            request=None, email="existing_member@example.com", password="legacy-password"
        )
        self.assertIn("access", tokens)

    @staticmethod
    def user_model():
        from django.contrib.auth import get_user_model

        return get_user_model()


class CustomUserTests(TestCase):
    def create_user(self, email="member@example.com", **kwargs):
        return get_user_model().objects.create_user(
            email=email, password="Valid-Password-927!", full_name="Member",
            phone_no="+255700000001", **kwargs,
        )

    def test_email_login_and_uuid_jwt_authentication(self):
        user = self.create_user()
        tokens = login_user(
            request=None, email=user.email, password="Valid-Password-927!"
        )
        request = APIRequestFactory().get(
            "/api/projects/", HTTP_AUTHORIZATION=f"Bearer {tokens['access']}"
        )
        authenticated_user, token = JWTAuthentication().authenticate(request)
        self.assertEqual(authenticated_user.pk, user.pk)
        self.assertEqual(token["user_id"], str(user.pk))

    def test_invalid_password_and_inactive_user_cannot_log_in(self):
        user = self.create_user()
        with self.assertRaises(AuthenticationFailed):
            login_user(request=None, email=user.email, password="wrong")
        user.is_active = False
        user.save(update_fields=["is_active"])
        with self.assertRaises(AuthenticationFailed):
            login_user(request=None, email=user.email, password="Valid-Password-927!")

    def test_duplicate_email_registration_returns_validation_error(self):
        self.create_user()
        with self.assertRaises(ValidationError) as caught:
            register_user(
                email="member@example.com", full_name="Another Member",
                phone_no="+255700000002", password="Another-Password-927!",
                password_confirm="Another-Password-927!",
            )
        self.assertIn("email", caught.exception.detail)

    def test_role_changes_update_user_privileges(self):
        role = Roles.objects.create(role_name="Manager", grant_superuser_access=True)
        user = self.create_user(role=role)
        self.assertTrue(user.is_superuser)
        role.grant_superuser_access = False
        role.save()
        user.refresh_from_db()
        self.assertFalse(user.is_superuser)

    def test_create_superuser_uses_custom_model(self):
        user = get_user_model().objects.create_superuser(
            email="admin@example.com", password="Admin-Password-927!",
            full_name="Admin", phone_no="+255700000003",
        )
        self.assertTrue(user.is_superuser)
        self.assertTrue(user.is_active)
        self.assertTrue(user.is_staff)

    def test_project_visibility(self):
        owner = self.create_user()
        other = self.create_user(email="other@example.com")
        admin = self.create_user(email="admin@example.com", is_superuser=True)
        own = Projects.objects.create(project_name="Own", user_id=owner)
        another = Projects.objects.create(project_name="Another", user_id=other)
        self.assertEqual(list(get_projects(user=owner)), [own])
        self.assertEqual(list(get_projects(user=other)), [another])
        self.assertCountEqual(get_projects(user=admin), [own, another])

    def test_task_status_database_constraint(self):
        user = self.create_user()
        project = Projects.objects.create(project_name="Project", user_id=user)
        for status in ("pending", "in_progress", "done"):
            Tasks.objects.create(task_name=status, status=status, project_id=project)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Tasks.objects.create(task_name="Invalid", status="invalid", project_id=project)


@override_settings(ROOT_URLCONF="STT.tests")
class AdminAccessTests(TestCase):
    def setUp(self):
        self.admin = get_user_model().objects.create_superuser(
            email="admin@example.com", password="Admin-Password-927!",
            full_name="Admin", phone_no="+255700000003",
        )

    def test_superuser_can_open_admin_and_user_add_form(self):
        self.assertTrue(self.client.login(
            email=self.admin.email, password="Admin-Password-927!"
        ))
        self.assertEqual(self.client.get("/admin/").status_code, 200)
        self.assertEqual(self.client.get("/admin/STT/users/add/").status_code, 200)

    def test_admin_can_create_another_admin_and_log_the_action(self):
        self.client.force_login(self.admin)
        response = self.client.post("/admin/STT/users/add/", {
            "email": "second_admin@example.com",
            "full_name": "Second Admin",
            "phone_no": "+255700000004",
            "password1": "Another-Admin-Password-927!",
            "password2": "Another-Admin-Password-927!",
            "is_active": "on", "is_staff": "on", "is_superuser": "on",
            "_save": "Save",
        })
        self.assertEqual(response.status_code, 302)
        user = get_user_model().objects.get(email="second_admin@example.com")
        self.assertTrue(user.is_staff and user.is_superuser)
        self.assertTrue(user.check_password("Another-Admin-Password-927!"))
        from django.contrib.admin.models import LogEntry
        self.assertTrue(LogEntry.objects.filter(user=self.admin, object_id=str(user.pk)).exists())

    def test_publicly_registered_user_cannot_access_admin(self):
        user = register_user(
            email="public@example.com", full_name="Public User", phone_no="+255700000005",
            password="Public-Password-927!", password_confirm="Public-Password-927!",
        )
        self.assertFalse(user.is_staff or user.is_superuser)
        self.client.force_login(user)
        response = self.client.get("/admin/")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login/", response.url)


class ProfilePictureStorageTests(TestCase):
    def setUp(self):
        from tempfile import TemporaryDirectory

        directory = self.enterContext(TemporaryDirectory())
        self.enterContext(override_settings(MEDIA_ROOT=directory))

    @staticmethod
    def image(name="profile.png"):
        from io import BytesIO
        from PIL import Image

        content = BytesIO()
        Image.new("RGB", (2, 2), color="blue").save(content, format="PNG")
        return SimpleUploadedFile(name, content.getvalue(), content_type="image/png")

    def register(self, picture):
        return register_user(
            email="picture@example.com", full_name="Picture User", phone_no="+255700000006",
            password="Picture-Password-927!", password_confirm="Picture-Password-927!",
            profile_picture=picture,
        )

    def test_registration_stores_image_and_database_keeps_path(self):
        user = self.register(self.image())
        user.refresh_from_db()
        self.assertTrue(user.profile_picture.name.startswith("profile_photos/"))
        self.assertTrue(user.profile_picture.storage.exists(user.profile_picture.name))
        self.assertTrue(user.profile_picture.url.startswith("/media/profile_photos/"))
        with user.profile_picture.open("rb") as picture:
            self.assertTrue(picture.read().startswith(b"\x89PNG"))

    def test_non_image_upload_is_rejected(self):
        upload = SimpleUploadedFile("fake.png", b"not an image", content_type="image/png")
        with self.assertRaises(ValidationError) as caught:
            self.register(upload)
        self.assertIn("profile_picture", caught.exception.detail)
        self.assertFalse(get_user_model().objects.exists())

    def test_replacement_deletes_previous_image_after_commit(self):
        user = self.register(self.image("old.png"))
        storage = user.profile_picture.storage
        previous_name = user.profile_picture.name
        user.profile_picture = self.image("new.png")
        with self.captureOnCommitCallbacks(execute=True):
            user.save()
            self.assertTrue(storage.exists(previous_name))
        self.assertFalse(storage.exists(previous_name))
        self.assertTrue(storage.exists(user.profile_picture.name))

    def test_unrelated_partial_save_keeps_existing_image(self):
        user = self.register(self.image("old.png"))
        storage = user.profile_picture.storage
        previous_name = user.profile_picture.name
        user.profile_picture = self.image("unsaved.png")
        user.full_name = "Updated Name"
        with self.captureOnCommitCallbacks(execute=True):
            user.save(update_fields=["full_name"])
        user.refresh_from_db()
        self.assertEqual(user.profile_picture.name, previous_name)
        self.assertTrue(storage.exists(previous_name))
