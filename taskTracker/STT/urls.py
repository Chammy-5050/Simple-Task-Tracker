from django.urls import path

from .views import (
    LoginView, MyProfilePictureView, ProjectListCreateView,
    ProjectTaskListCreateView, RegisterView,
)


app_name = "STT"

urlpatterns = [
    path(
        "projects/<uuid:project_id>/tasks/",
        ProjectTaskListCreateView.as_view(),
        name="project-tasks",
    ),
    path("users/me/", MyProfilePictureView.as_view(), name="my-profile-picture"),
    path("projects/", ProjectListCreateView.as_view(), name="project-list"),
    path("auth/register/", RegisterView.as_view(), name="register"),
    path("auth/login/", LoginView.as_view(), name="login"),
]
