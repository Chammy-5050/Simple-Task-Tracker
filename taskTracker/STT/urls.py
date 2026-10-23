from django.urls import path

from .views import LoginView, ProjectListView, RegisterView


app_name = "STT"

urlpatterns = [
    path("projects/", ProjectListView.as_view(), name="project-list"),
    path("auth/register/", RegisterView.as_view(), name="register"),
    path("auth/login/", LoginView.as_view(), name="login"),
]
