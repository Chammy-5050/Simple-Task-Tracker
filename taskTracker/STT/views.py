from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .serializers import LoginSerializer
from .services import login_user


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
