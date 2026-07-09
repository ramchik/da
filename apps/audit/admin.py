from django.contrib import admin

from .models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    """Read-only: the audit trail cannot be edited or deleted from the UI."""

    list_display = ("timestamp", "actor", "action", "model_label", "object_pk", "object_repr")
    list_filter = ("action", "model_label")
    search_fields = ("object_pk", "object_repr", "actor__username")
    date_hierarchy = "timestamp"
    readonly_fields = ("timestamp", "actor", "action", "model_label", "object_pk",
                       "object_repr", "changes")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
