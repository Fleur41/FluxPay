from django.contrib import admin
from django.contrib.auth.admin import GroupAdmin as BaseGroupAdmin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import Group
from unfold.admin import ModelAdmin
from unfold.contrib.filters.admin import RangeDateFilter
from unfold.decorators import display
from unfold.forms import AdminPasswordChangeForm, UserChangeForm, UserCreationForm

from .models import User

admin.site.unregister(Group)


@admin.register(Group)
class GroupAdmin(BaseGroupAdmin, ModelAdmin):
    """Staff groups, e.g. "Support" with the "Can top up or correct customer wallets" permission."""


@admin.register(User)
class UserAdmin(BaseUserAdmin, ModelAdmin):
    form = UserChangeForm
    add_form = UserCreationForm
    change_password_form = AdminPasswordChangeForm
    warn_unsaved_form = True
    list_filter_submit = True

    ordering = ("-date_joined",)
    list_display = ("email", "full_name", "phone_number", "role", "status", "date_joined")
    list_filter = ("is_staff", "is_active", ("date_joined", RangeDateFilter))
    search_fields = ("email", "full_name", "phone_number")
    search_help_text = "Search by email, name or phone number"
    readonly_fields = ("last_login", "date_joined")
    fieldsets = (
        ("Account", {"fields": ("email", "password")}),
        ("Profile", {"fields": ("full_name", "phone_number")}),
        (
            "Access",
            {
                "fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions"),
                "description": "Staff can sign in to this back-office. Give them only the permissions their job needs.",
            },
        ),
        ("Dates", {"fields": ("last_login", "date_joined"), "classes": ["tab"]}),
    )
    add_fieldsets = ((None, {"classes": ("wide",), "fields": ("email", "full_name", "password1", "password2")}),)

    @display(description="Role", label={"Admin": "danger", "Staff": "primary", "Customer": "info", "System": ""})
    def role(self, user):
        if user.email.endswith("@fluxpay.internal"):
            return "System"
        if user.is_superuser:
            return "Admin"
        return "Staff" if user.is_staff else "Customer"

    @display(description="Status", label={"Active": "success", "Disabled": "danger"})
    def status(self, user):
        return "Active" if user.is_active else "Disabled"
