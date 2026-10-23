from django.contrib.auth import get_user_model
from django.contrib import admin
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.http import Http404
from django.test import TestCase, override_settings
from django.urls import path
from rest_framework.exceptions import AuthenticationFailed, NotAuthenticated, PermissionDenied, ValidationError
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.test import APIClient, APIRequestFactory
from rest_framework_simplejwt.tokens import RefreshToken

from .models import Projects, Roles, Tasks
from .services import (
    create_project, get_projects, login_user, register_user, update_profile_picture,
    create_project_task, get_project_tasks,
)

urlpatterns = [path("admin/", admin.site.urls)]


@override_settings(ROOT_URLCONF="taskTracker.urls")
class TeamAdminApiTests(TestCase):
    def setUp(self):
        self.admin = get_user_model().objects.create_superuser(email="team_admin@example.com")
        self.member = get_user_model().objects.create_user(email="member@example.com")
        self.project = Projects.objects.create(project_name="Member project", user_id=self.member)
        self.task = Tasks.objects.create(task_name="Member task", project_id=self.project)
        self.api = APIClient()
        self.api.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(self.admin).access_token}")

    def test_admin_sees_all_projects_and_tasks(self):
        response = self.api.get("/api/projects/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(str(response.data[0]["project_id"]), str(self.project.pk))
        response = self.api.get(f"/api/projects/{self.project.pk}/tasks/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(str(response.data[0]["task_id"]), str(self.task.pk))

    def test_admin_cannot_list_create_or_configure_users(self):
        for method, path in (("get", "/api/admin/users/"), ("post", "/api/admin/users/"), ("patch", f"/api/admin/users/{self.member.pk}/")):
            with self.subTest(method=method):
                response = getattr(self.api, method)(path, {"email": "forbidden@example.com"}, format="json")
                self.assertEqual(response.status_code, 404)
        self.assertFalse(get_user_model().objects.filter(email="forbidden@example.com").exists())

    def test_normal_user_still_cannot_access_another_members_project(self):
        other = get_user_model().objects.create_user(email="other_member@example.com")
        self.api.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(other).access_token}")
        self.assertEqual(self.api.get("/api/projects/").data, [])
        self.assertEqual(self.api.get(f"/api/projects/{self.project.pk}/tasks/").status_code, 404)


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

    def test_superuser_can_open_work_admin_but_not_user_add_form(self):
        self.assertTrue(self.client.login(
            email=self.admin.email, password="Admin-Password-927!"
        ))
        self.assertEqual(self.client.get("/admin/").status_code, 200)
        self.assertEqual(self.client.get("/admin/STT/projects/").status_code, 200)
        self.assertEqual(self.client.get("/admin/STT/tasks/").status_code, 200)
        self.assertEqual(self.client.get("/admin/STT/users/add/").status_code, 404)

    def test_admin_cannot_create_another_user(self):
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
        self.assertEqual(response.status_code, 404)
        self.assertFalse(get_user_model().objects.filter(email="second_admin@example.com").exists())

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

    def user_with_picture(self, picture):
        return get_user_model().objects.create_user(
            email="picture@example.com", full_name="Picture User", phone_no="+255700000006",
            password="Picture-Password-927!",
            profile_picture=picture,
        )

    def test_model_stores_image_and_database_keeps_path(self):
        user = self.user_with_picture(self.image())
        user.refresh_from_db()
        self.assertTrue(user.profile_picture.name.startswith("profile_photos/"))
        self.assertTrue(user.profile_picture.storage.exists(user.profile_picture.name))
        self.assertTrue(user.profile_picture.url.startswith("/media/profile_photos/"))
        with user.profile_picture.open("rb") as picture:
            self.assertTrue(picture.read().startswith(b"\x89PNG"))

    def test_admin_form_rejects_non_image_upload(self):
        from django.forms import modelform_factory

        PictureForm = modelform_factory(get_user_model(), fields=["profile_picture"])
        upload = SimpleUploadedFile("fake.png", b"not an image", content_type="image/png")
        form = PictureForm(data={}, files={"profile_picture": upload})
        self.assertFalse(form.is_valid())
        self.assertIn("profile_picture", form.errors)
        self.assertFalse(get_user_model().objects.exists())

    def test_replacement_deletes_previous_image_after_commit(self):
        user = self.user_with_picture(self.image("old.png"))
        storage = user.profile_picture.storage
        previous_name = user.profile_picture.name
        user.profile_picture = self.image("new.png")
        with self.captureOnCommitCallbacks(execute=True):
            user.save()
            self.assertTrue(storage.exists(previous_name))
        self.assertFalse(storage.exists(previous_name))
        self.assertTrue(storage.exists(user.profile_picture.name))

    def test_unrelated_partial_save_keeps_existing_image(self):
        user = self.user_with_picture(self.image("old.png"))
        storage = user.profile_picture.storage
        previous_name = user.profile_picture.name
        user.profile_picture = self.image("unsaved.png")
        user.full_name = "Updated Name"
        with self.captureOnCommitCallbacks(execute=True):
            user.save(update_fields=["full_name"])
        user.refresh_from_db()
        self.assertEqual(user.profile_picture.name, previous_name)
        self.assertTrue(storage.exists(previous_name))


class ProjectCreationTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            email="creator@example.com", full_name="Creator", phone_no="+255700000007",
        )

    def test_creation_sets_owner_and_allows_optional_description(self):
        project = create_project(user=self.user, project_name="New Project")
        project.refresh_from_db()
        self.assertEqual(project.user_id, self.user)
        self.assertEqual(project.description, "")
        self.assertEqual(list(get_projects(user=self.user)), [project])

    def test_description_is_saved(self):
        project = create_project(
            user=self.user, project_name="Described", description="Project details"
        )
        self.assertEqual(project.description, "Project details")

    def test_duplicate_name_returns_field_error(self):
        create_project(user=self.user, project_name="Duplicate")
        with self.assertRaises(ValidationError) as caught:
            create_project(user=self.user, project_name="Duplicate")
        self.assertIn("project_name", caught.exception.detail)
        self.assertEqual(Projects.objects.count(), 1)

    def test_invalid_fields_are_rejected_without_creating_projects(self):
        for name, description in (("", ""), ("x" * 256, ""), ("Valid", "x" * 256)):
            with self.subTest(name=name, description=description):
                with self.assertRaises(ValidationError):
                    create_project(user=self.user, project_name=name, description=description)
        self.assertFalse(Projects.objects.exists())


    def test_unauthenticated_and_inactive_users_cannot_create_projects(self):
        from django.contrib.auth.models import AnonymousUser

        self.user.is_active = False
        for user in (None, AnonymousUser(), self.user):
            with self.subTest(user=user):
                with self.assertRaises(NotAuthenticated):
                    create_project(user=user, project_name="Forbidden")
        self.assertFalse(Projects.objects.exists())


class ProfilePictureUpdateTests(TestCase):
    def setUp(self):
        from tempfile import TemporaryDirectory

        directory = self.enterContext(TemporaryDirectory())
        self.enterContext(override_settings(MEDIA_ROOT=directory))
        self.user = get_user_model().objects.create_user(
            email="picture_owner@example.com", full_name="Picture Owner",
            phone_no="+255700000008",
        )

    def test_upload_only_updates_signed_in_user(self):
        other = get_user_model().objects.create_user(email="other@example.com")
        account = update_profile_picture(
            user=self.user, profile_picture=ProfilePictureStorageTests.image()
        )
        self.user.refresh_from_db()
        other.refresh_from_db()
        self.assertEqual(account.pk, self.user.pk)
        self.assertTrue(self.user.profile_picture.storage.exists(self.user.profile_picture.name))
        self.assertFalse(other.profile_picture)
        self.assertFalse(self.user.is_staff or self.user.is_superuser)
        self.assertEqual(self.user.full_name, "Picture Owner")

    def test_replacement_removes_old_picture_after_commit(self):
        user = update_profile_picture(
            user=self.user, profile_picture=ProfilePictureStorageTests.image("first.png")
        )
        old_name = user.profile_picture.name
        storage = user.profile_picture.storage
        with self.captureOnCommitCallbacks(execute=True):
            updated = update_profile_picture(
                user=self.user, profile_picture=ProfilePictureStorageTests.image("second.png")
            )
            self.assertTrue(storage.exists(old_name))
        self.assertFalse(storage.exists(old_name))
        self.assertTrue(storage.exists(updated.profile_picture.name))

    def test_missing_and_invalid_images_are_rejected(self):
        for image in (None, SimpleUploadedFile("fake.png", b"invalid", content_type="image/png")):
            with self.subTest(image=image):
                with self.assertRaises(ValidationError) as caught:
                    update_profile_picture(user=self.user, profile_picture=image)
                self.assertIn("profile_picture", caught.exception.detail)
        self.user.refresh_from_db()
        self.assertFalse(self.user.profile_picture)

    def test_inactive_and_anonymous_users_are_rejected(self):
        from django.contrib.auth.models import AnonymousUser

        self.user.is_active = False
        for user in (None, AnonymousUser(), self.user):
            with self.subTest(user=user):
                with self.assertRaises(NotAuthenticated):
                    update_profile_picture(
                        user=user, profile_picture=ProfilePictureStorageTests.image()
                    )


class ProjectTaskTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.owner = User.objects.create_user(email="task_owner@example.com")
        cls.other = User.objects.create_user(email="task_other@example.com")
        cls.admin = User.objects.create_superuser(email="task_admin@example.com")
        cls.project = Projects.objects.create(project_name="Task project", user_id=cls.owner)
        cls.other_project = Projects.objects.create(project_name="Other project", user_id=cls.other)
        cls.task = Tasks.objects.create(task_name="Existing task", project_id=cls.project)
        cls.other_task = Tasks.objects.create(task_name="Other task", project_id=cls.other_project)

    def test_list_only_returns_tasks_in_selected_project(self):
        self.assertEqual(
            list(get_project_tasks(user=self.owner, project_id=self.project.pk)), [self.task]
        )
        self.assertEqual(
            list(get_project_tasks(user=self.admin, project_id=self.other_project.pk)),
            [self.other_task],
        )

    def test_other_users_cannot_read_or_create_tasks_in_project(self):
        with self.assertRaises(Http404):
            get_project_tasks(user=self.other, project_id=self.project.pk)
        with self.assertRaises(Http404):
            create_project_task(
                user=self.other, project_id=self.project.pk, task_name="Forbidden"
            )
        self.assertFalse(Tasks.objects.filter(task_name="Forbidden").exists())

    def test_owner_creates_task_with_defaults(self):
        task = create_project_task(
            user=self.owner, project_id=self.project.pk, task_name="New task"
        )
        task.refresh_from_db()
        self.assertEqual(task.project_id, self.project)
        self.assertEqual(task.status, "pending")
        self.assertEqual(task.description, "")

    def test_admin_cannot_create_task_in_another_users_project(self):
        with self.assertRaises(PermissionDenied):
            create_project_task(
                user=self.admin, project_id=self.other_project.pk,
                task_name="Admin task", description="Details", status="in_progress",
            )
        self.assertFalse(Tasks.objects.filter(task_name="Admin task").exists())

    def test_invalid_fields_and_duplicates_return_validation_errors(self):
        for name, status in (("", "pending"), ("x" * 256, "pending"), ("Valid", "invalid"), ("Existing task", "pending")):
            with self.subTest(name=name, status=status):
                with self.assertRaises(ValidationError):
                    create_project_task(
                        user=self.owner, project_id=self.project.pk,
                        task_name=name, status=status,
                    )
        self.assertEqual(Tasks.objects.count(), 2)

    def test_unknown_project_returns_not_found(self):
        import uuid

        project_id = uuid.uuid4()
        with self.assertRaises(Http404):
            get_project_tasks(user=self.admin, project_id=project_id)
        with self.assertRaises(Http404):
            create_project_task(user=self.admin, project_id=project_id, task_name="Missing")

    def test_anonymous_and_inactive_users_cannot_list_or_create_tasks(self):
        from django.contrib.auth.models import AnonymousUser

        self.owner.is_active = False
        for user in (None, AnonymousUser(), self.owner):
            with self.subTest(user=user):
                with self.assertRaises(NotAuthenticated):
                    get_project_tasks(user=user, project_id=self.project.pk)
                with self.assertRaises(NotAuthenticated):
                    create_project_task(user=user, project_id=self.project.pk, task_name="Denied")
