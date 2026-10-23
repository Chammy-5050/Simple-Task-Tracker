from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication

from .serializers import LoginSerializer, ProjectSerializer, RegisterSerializer
from .services import get_projects, login_user, register_user


class LoginView(APIView):
    """POST /api/auth/login/ with an email and password.

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
            email=serializer.validated_data["email"],
            password=serializer.validated_data["password"],
        )

        response = Response(tokens, status=status.HTTP_200_OK)
        response["Cache-Control"] = "no-store"
        response["Pragma"] = "no-cache"
        return response


class RegisterView(APIView):
    """Accept registration fields and an optional multipart profile_picture.

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
            email=serializer.validated_data["email"],
            full_name=serializer.validated_data["full_name"],
            phone_no=serializer.validated_data["phone_no"],
            password=serializer.validated_data["password"],
            password_confirm=serializer.validated_data.get("password_confirm"),
            profile_picture=serializer.validated_data.get("profile_picture"),
        )

        return Response(
            {
                "user_id": user.pk,
                "full_name": user.full_name,
                "email": user.email,
                "profile_picture": (
                    request.build_absolute_uri(user.profile_picture.url)
                    if user.profile_picture else None
                ),
            },
            status=status.HTTP_201_CREATED,
        )


class ProjectListView(APIView):
    """Retrieve the signed-in user's projects, or all projects for admins."""

    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "head", "options"]

    def get(self, request):
        projects = get_projects(user=request.user)
        serializer = ProjectSerializer(
            projects, many=True, context={"request": request}
        )
        return Response(serializer.data, status=status.HTTP_200_OK)
