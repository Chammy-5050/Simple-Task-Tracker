from django.urls import path

from .views import LoginView


app_name = "STT"

urlpatterns = [
    path("auth/login/", LoginView.as_view(), name="login"),
]
