from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from .views import (
    LoginView, MyProfilePictureView, ProjectListCreateView,
    ProjectDetailView, ProjectTaskListCreateView, RegisterView,
    PasswordChangeView, TaskUpdateView,
)


app_name = "STT"

urlpatterns = [
    path("auth/refresh/", TokenRefreshView.as_view(), name="token-refresh"),
    path("users/me/password/", PasswordChangeView.as_view(), name="password-change"),
    path("projects/<uuid:project_id>/tasks/<uuid:task_id>/", TaskUpdateView.as_view(), name="task-update"),
    path(
        "projects/<uuid:project_id>/tasks/",
        ProjectTaskListCreateView.as_view(),
        name="project-tasks",
    ),
    path("projects/<uuid:project_id>/", ProjectDetailView.as_view(), name="project-detail"),
    path("users/me/", MyProfilePictureView.as_view(), name="my-profile-picture"),
    path("projects/", ProjectListCreateView.as_view(), name="project-list"),
    path("auth/register/", RegisterView.as_view(), name="register"),
    path("auth/login/", LoginView.as_view(), name="login"),
]
