from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.forms import UserChangeForm, UserCreationForm

from .models import Projects, Tasks, Users
from django.contrib.auth.models import Group


class AdminUserCreationForm(UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = Users
        fields = ("email", "full_name", "phone_no")


class AdminUserChangeForm(UserChangeForm):
    class Meta(UserChangeForm.Meta):
        model = Users
        fields = "__all__"


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


# Team admins use Django admin for work records, not user administration.
if admin.site.is_registered(Users):
    admin.site.unregister(Users)
if admin.site.is_registered(Group):
    admin.site.unregister(Group)
class OwnedWorkAdmin(admin.ModelAdmin):
    """Team admins may view all work, but may only modify their own."""
    actions = None

    def _owns(self, request, obj):
        owner_id = obj.user_id_id if isinstance(obj, Projects) else obj.project_id.user_id_id
        return owner_id == request.user.pk

    def has_change_permission(self, request, obj=None):
        return super().has_change_permission(request, obj) and (obj is None or self._owns(request, obj))

    def has_delete_permission(self, request, obj=None):
        return super().has_delete_permission(request, obj) and (obj is None or self._owns(request, obj))

    def get_readonly_fields(self, request, obj=None):
        return ("user_id",) if self.model is Projects else ()

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if self.model is Tasks and db_field.name == "project_id":
            kwargs["queryset"] = Projects.objects.filter(user_id=request.user)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def save_model(self, request, obj, form, change):
        if isinstance(obj, Projects) and not change:
            obj.user_id = request.user
        super().save_model(request, obj, form, change)


admin.site.register(Projects, OwnedWorkAdmin)
admin.site.register(Tasks, OwnedWorkAdmin)


