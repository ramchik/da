from django.contrib import admin

from .models import Alert


@admin.register(Alert)
class AlertAdmin(admin.ModelAdmin):
    list_display = ("rule_code", "severity", "patient", "status",
                    "first_raised_at", "resolved_by")
    list_filter = ("severity", "status", "rule_code")
    search_fields = ("patient__registry_code", "patient__last_name", "message")
    date_hierarchy = "first_raised_at"
    readonly_fields = ("first_raised_at", "last_evaluated_at")
