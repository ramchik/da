from django.contrib import admin

from .models import FollowUpTask


@admin.register(FollowUpTask)
class FollowUpTaskAdmin(admin.ModelAdmin):
    list_display = ("title", "task_type", "patient", "due_date", "status",
                    "assigned_role", "assigned_to", "source")
    list_filter = ("status", "task_type", "assigned_role", "source")
    search_fields = ("title", "patient__registry_code", "patient__last_name")
    date_hierarchy = "due_date"
    autocomplete_fields = ("patient",)
