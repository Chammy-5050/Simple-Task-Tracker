from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .serializers import LoginSerializer, RegisterSerializer
from .services import login_user, register_user


class LoginView(APIView):
    """POST /api/auth/login/ with a username and password.

    LoginSerializer validates the input fields. The login_user service must
    verify credentials, reject inactive users, and return access/refresh tokens.
    Invalid credentials must raise DRF's AuthenticationFailed exception.
    """

    authentication_classes = []
    permission_classes = [AllowAny]
    http_method_names = ["post", "options"]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        tokens = login_user(
            request=request,
            username=serializer.validated_data["username"],
            password=serializer.validated_data["password"],
        )

        response = Response(tokens, status=status.HTTP_200_OK)
        response["Cache-Control"] = "no-store"
        response["Pragma"] = "no-cache"
        return response


class RegisterView(APIView):
    """Accept username, password, password_confirm, and optional email.

    RegisterSerializer must preserve passwords exactly and mark both password
    fields write_only=True; neither field should trim whitespace.
    """

    authentication_classes = []
    permission_classes = [AllowAny]
    http_method_names = ["post", "options"]

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = register_user(
            username=serializer.validated_data["username"],
            password=serializer.validated_data["password"],
            password_confirm=serializer.validated_data.get("password_confirm"),
            email=serializer.validated_data.get("email", ""),
        )

        return Response(
            {"id": user.pk, "username": user.username, "email": user.email},
            status=status.HTTP_201_CREATED,
        )
