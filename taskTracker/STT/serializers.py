from django.contrib.auth import get_user_model
from rest_framework import serializers
from rest_framework_simplejwt.exceptions import InvalidToken
from rest_framework_simplejwt.serializers import TokenRefreshSerializer
from rest_framework_simplejwt.settings import api_settings
from rest_framework_simplejwt.utils import get_md5_hash_password

from notifications.models import VerificationCode

from .models import Projects, Tasks, Users


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, trim_whitespace=False)


class RegisterSerializer(serializers.Serializer):
    full_name = serializers.CharField(max_length=255)
    phone_no = serializers.CharField(max_length=20)
    password = serializers.CharField(write_only=True, trim_whitespace=False)
    password_confirm = serializers.CharField(write_only=True, trim_whitespace=False)
    email = serializers.EmailField(max_length=255)


class CreatorSerializer(serializers.ModelSerializer):
    """Public attribution only; do not disclose contact details or privileges."""
    class Meta:
        model = Users
        fields = ("user_id", "full_name", "profile_picture")
        read_only_fields = fields


class ProjectSerializer(serializers.ModelSerializer):
    creator = CreatorSerializer(source="user_id", read_only=True)
    class Meta:
        model = Projects
        fields = ("project_id", "project_name", "description", "user_id", "creator", "created_at", "updated_at")
        read_only_fields = ("project_id", "user_id", "created_at", "updated_at")


class TaskSerializer(serializers.ModelSerializer):
    creator = CreatorSerializer(source="project_id.user_id", read_only=True)
    can_edit = serializers.SerializerMethodField()

    def get_can_edit(self, task):
        request = self.context.get("request")
        return bool(request and request.user.is_authenticated and request.user.is_active and task.project_id.user_id_id == request.user.pk)

    class Meta:
        model = Tasks
        fields = ("task_id", "task_name", "description", "status", "due_date", "project_id", "creator", "can_edit", "created_at", "updated_at")
        read_only_fields = ("task_id", "project_id", "created_at", "updated_at")


class ProfilePictureSerializer(serializers.Serializer):
    profile_picture = serializers.ImageField()


class UserProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = Users
        fields = ("user_id", "full_name", "email", "phone_no", "profile_picture", "is_active", "is_staff", "is_superuser", "role")
        read_only_fields = ("user_id", "profile_picture", "is_active", "is_staff", "is_superuser", "role")


class PasswordChangeSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True, trim_whitespace=False)
    password = serializers.CharField(write_only=True, trim_whitespace=False)
    password_confirm = serializers.CharField(write_only=True, trim_whitespace=False)


class RevocableTokenRefreshSerializer(TokenRefreshSerializer):
    """Refuse refresh tokens issued before the account's password last changed.

    simplejwt only checks the revoke claim on access tokens; without this a stale
    refresh token would keep minting access tokens that are then rejected.
    """

    def validate(self, attrs):
        refresh = self.token_class(attrs["refresh"])
        user = get_user_model().objects.filter(
            **{api_settings.USER_ID_FIELD: refresh.payload.get(api_settings.USER_ID_CLAIM)}
        ).first()
        if user is None or refresh.payload.get(api_settings.REVOKE_TOKEN_CLAIM) != get_md5_hash_password(user.password):
            raise InvalidToken("This session has ended. Sign in again.")
        return super().validate(attrs)


CODE_FIELD = {"min_length": 6, "max_length": 6, "trim_whitespace": True}


class VerifyEmailSerializer(serializers.Serializer):
    email = serializers.EmailField(max_length=255)
    code = serializers.RegexField(r"^\d{6}$", error_messages={"invalid": "Enter the 6-digit code."}, **CODE_FIELD)


class ResendCodeSerializer(serializers.Serializer):
    email = serializers.EmailField(max_length=255)
    purpose = serializers.ChoiceField(choices=[value for value, _ in VerificationCode.PURPOSES])


class ForgotPasswordSerializer(serializers.Serializer):
    email = serializers.EmailField(max_length=255)


class VerifyResetCodeSerializer(VerifyEmailSerializer):
    pass


class ResetPasswordSerializer(serializers.Serializer):
    reset_token = serializers.CharField()
    password = serializers.CharField(write_only=True, trim_whitespace=False)
    confirm_password = serializers.CharField(write_only=True, trim_whitespace=False)
