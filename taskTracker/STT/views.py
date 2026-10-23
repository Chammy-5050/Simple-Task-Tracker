from rest_framework import status
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication

from .serializers import (
    LoginSerializer, ProfilePictureSerializer, ProjectSerializer, RegisterSerializer,
    TaskSerializer,
    PasswordChangeSerializer, UserProfileSerializer,
)
from .services import (
    create_project, get_projects, login_user, register_user, update_profile_picture,
    create_project_task, get_project_tasks,
    change_user_password, update_task, update_user_profile,
)


class LoginView(APIView):
    """POST /api/auth/login/ with an email and password.

    LoginSerializer validates the input fields. The login_user service must
    verify credentials, reject inactive users, and return access/refresh tokens.
    Invalid credentials must raise DRF's AuthenticationFailed exception.
    """

    authentication_classes = []
    permission_classes = [AllowAny]
    http_method_names = ["post", "options"]

    def get_authenticate_header(self, request):
        # Preserve HTTP 401 for rejected credentials on this public endpoint.
        return JWTAuthentication().authenticate_header(request)

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
    """Accept email, full_name, phone_no, password, and password_confirm.

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
        )

        return Response(
            {
                "user_id": user.pk,
                "full_name": user.full_name,
                "email": user.email,
            },
            status=status.HTTP_201_CREATED,
        )


class ProjectListCreateView(APIView):
    """List visible projects or create a project owned by the signed-in user.

    ProjectSerializer accepts project_name and optional description. Ownership,
    project_id, and timestamps must be read-only serializer fields.
    """

    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "post", "head", "options"]

    def get(self, request):
        projects = get_projects(user=request.user)
        serializer = ProjectSerializer(
            projects, many=True, context={"request": request}
        )
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request):
        serializer = ProjectSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        project = create_project(
            user=request.user,
            project_name=serializer.validated_data["project_name"],
            description=serializer.validated_data.get("description", ""),
        )
        output = ProjectSerializer(project, context={"request": request})
        return Response(output.data, status=status.HTTP_201_CREATED)


class MyProfilePictureView(APIView):
    """PATCH /api/users/me/ accepts a multipart profile_picture image.

    ProfilePictureSerializer must require an ImageField named profile_picture.
    Account IDs and privilege fields are never used to select or update a user.
    """

    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]
    parser_classes = [JSONParser, MultiPartParser, FormParser]
    http_method_names = ["get", "patch", "options"]

    def get(self, request):
        return Response(UserProfileSerializer(request.user, context={"request": request}).data)

    def patch(self, request):
        if "profile_picture" not in request.data:
            if not any(field in request.data for field in ("full_name", "email", "phone_no")):
                raise ValidationError({"detail": "Provide profile fields or a profile_picture."})
            serializer = UserProfileSerializer(request.user, data=request.data, partial=True)
            serializer.is_valid(raise_exception=True)
            user = update_user_profile(user=request.user, changes=serializer.validated_data)
            return Response(UserProfileSerializer(user, context={"request": request}).data)
        serializer = ProfilePictureSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        user = update_profile_picture(
            user=request.user,
            profile_picture=serializer.validated_data.get("profile_picture"),
        )
        return Response(
            {
                "user_id": user.pk,
                "profile_picture": request.build_absolute_uri(user.profile_picture.url),
            },
            status=status.HTTP_200_OK,
        )


class ProjectTaskListCreateView(APIView):
    """List or create tasks in an authorized project.

    TaskSerializer accepts task_name, optional description, and optional status.
    task_id, project_id, created_at, and updated_at must be read-only.
    """

    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "post", "head", "options"]

    def get(self, request, project_id):
        tasks = get_project_tasks(user=request.user, project_id=project_id)
        serializer = TaskSerializer(tasks, many=True, context={"request": request})
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request, project_id):
        # Check project access before validating or disclosing task-name conflicts.
        get_project_tasks(user=request.user, project_id=project_id)
        serializer = TaskSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        task = create_project_task(
            user=request.user,
            project_id=project_id,
            task_name=serializer.validated_data["task_name"],
            description=serializer.validated_data.get("description", ""),
            status=serializer.validated_data.get("status", "pending"),
            due_date=serializer.validated_data.get("due_date"),
        )
        output = TaskSerializer(task, context={"request": request})
        return Response(output.data, status=status.HTTP_201_CREATED)


class TaskUpdateView(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request, project_id, task_id):
        get_project_tasks(user=request.user, project_id=project_id)
        serializer = TaskSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        task = update_task(user=request.user, project_id=project_id, task_id=task_id, changes=serializer.validated_data)
        return Response(TaskSerializer(task, context={"request": request}).data)


class PasswordChangeView(APIView):
    def post(self, request):
        serializer = PasswordChangeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        change_user_password(user=request.user, **serializer.validated_data)
        return Response({"detail": "Password updated."})
