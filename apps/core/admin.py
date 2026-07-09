from django.contrib import admin

from .models import RegistrySetting


@admin.register(RegistrySetting)
class RegistrySettingAdmin(admin.ModelAdmin):
    list_display = ("key", "value", "description", "updated_by", "updated_at")
    readonly_fields = ("updated_by", "updated_at")

    def save_model(self, request, obj, form, change):
        obj.updated_by = request.user
        super().save_model(request, obj, form, change)
