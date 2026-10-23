from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.forms import UserChangeForm, UserCreationForm

from .models import Users


class AdminUserCreationForm(UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = Users
        fields = ("email", "full_name", "phone_no")


class AdminUserChangeForm(UserChangeForm):
    class Meta(UserChangeForm.Meta):
        model = Users
        fields = "__all__"


@admin.register(Users)
class UsersAdmin(UserAdmin):
    def get_queryset(self, request):
        return super().get_queryset(request).filter(is_staff=True, is_superuser=False)

    def save_model(self, request, obj, form, change):
        obj.is_staff = True
        obj.is_superuser = False
        obj.role = None
        super().save_model(request, obj, form, change)

    form = AdminUserChangeForm
    add_form = AdminUserCreationForm
    list_display = ("email", "full_name", "is_active", "is_staff", "is_superuser")
    list_filter = ("is_active", "is_staff", "is_superuser", "role")
    search_fields = ("email", "full_name", "phone_no")
    ordering = ("email",)
    filter_horizontal = ()
    readonly_fields = ("user_id", "created_at", "updated_at", "last_login")
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Profile", {"fields": ("full_name", "phone_no", "profile_picture")}),
        ("Access", {"fields": ("is_active",)}),
        ("Dates", {"fields": ("user_id", "last_login", "created_at", "updated_at")}),
    )
    add_fieldsets = (
        (None, {"classes": ("wide",), "fields": (
            "email", "full_name", "phone_no", "password1", "password2",
            "is_active",
        )}),
    )


