from django.contrib import admin

from .models import ExportLog


@admin.register(ExportLog)
class ExportLogAdmin(admin.ModelAdmin):
    """Read-only: export history is written by the export view only."""

    list_display = ("exported_at", "requested_by", "dataset", "row_count")
    list_filter = ("dataset",)
    date_hierarchy = "exported_at"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
