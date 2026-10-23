from rest_framework import serializers

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
