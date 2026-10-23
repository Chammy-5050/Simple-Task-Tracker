from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient
from .models import Projects


class ProjectCreationPermissionsTests(TestCase):
    def test_admin_cannot_create_projects(self):
        admin = get_user_model().objects.create_superuser(email="admin_project@example.test")
        client = APIClient()
        client.force_authenticate(admin)
        response = client.post("/api/projects/", {"project_name": "Forbidden project"}, format="json")
        self.assertEqual(response.status_code, 403)
        client.force_login(admin)
        self.assertEqual(client.get("/admin/STT/projects/add/").status_code, 403)
        self.assertFalse(Projects.objects.filter(project_name="Forbidden project").exists())
