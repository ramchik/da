from django.contrib import admin

from .models import DialysisSessionLog


@admin.register(DialysisSessionLog)
class DialysisSessionLogAdmin(admin.ModelAdmin):
    list_display = ("access", "session_date", "cannulation_successful",
                    "blood_flow_rate_ml_min", "problem", "session_completed", "recorded_by")
    list_filter = ("problem", "session_completed", "cannulation_successful")
    search_fields = ("access__patient__registry_code", "access__patient__last_name")
    date_hierarchy = "session_date"
