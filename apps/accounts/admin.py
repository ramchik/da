from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import User


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    fieldsets = DjangoUserAdmin.fieldsets + (
        ("Registry role", {"fields": ("role", "phone", "institution")}),
    )
    add_fieldsets = DjangoUserAdmin.add_fieldsets + (
        ("Registry role", {"fields": ("role", "phone", "institution")}),
    )
    list_display = ("username", "first_name", "last_name", "role", "institution", "is_active")
    list_filter = ("role", "is_active", "is_staff")
    search_fields = ("username", "first_name", "last_name", "email")
