from django.contrib import admin

from .models import (
    AccessComplication,
    AccessPlan,
    AccessProcedure,
    CatheterDetail,
    Device,
    InfectionDetail,
    MaturationAssessment,
    ProcedureDevice,
    ThrombosisDysfunctionDetail,
    VascularAccess,
    VesselMapping,
)


@admin.register(VesselMapping)
class VesselMappingAdmin(admin.ModelAdmin):
    list_display = ("patient", "exam_date", "side", "cephalic_vein_diameter_mm",
                    "basilic_vein_diameter_mm", "radial_artery_diameter_mm", "performed_by")
    list_filter = ("side", "arterial_calcification", "central_vein_patency_concern")
    search_fields = ("patient__registry_code", "patient__last_name")
    date_hierarchy = "exam_date"


@admin.register(AccessPlan)
class AccessPlanAdmin(admin.ModelAdmin):
    list_display = ("patient", "plan_date", "planned_access_type", "planned_side", "status", "planned_by")
    list_filter = ("planned_access_type", "planned_side", "status")
    search_fields = ("patient__registry_code", "patient__last_name")
    date_hierarchy = "plan_date"


class AccessProcedureInline(admin.TabularInline):
    model = AccessProcedure
    extra = 0
    fields = ("procedure_type", "performed_on", "operator", "urgency",
              "indication_complication", "technical_success")


class AccessComplicationInline(admin.TabularInline):
    model = AccessComplication
    extra = 0
    fields = ("complication_type", "onset_date", "triage_status", "management",
              "resolved", "resolution_date")


class CatheterDetailInline(admin.StackedInline):
    model = CatheterDetail
    extra = 0


class MaturationAssessmentInline(admin.TabularInline):
    model = MaturationAssessment
    extra = 0
    fields = ("assessment_date", "assessment_type", "thrill_present", "bruit_present",
              "outflow_vein_diameter_mm", "flow_volume_ml_min", "verdict", "assessed_by")


@admin.register(VascularAccess)
class VascularAccessAdmin(admin.ModelAdmin):
    list_display = ("patient", "access_type", "laterality", "site", "created_on",
                    "status", "first_successful_cannulation_on", "abandoned_on")
    list_filter = ("access_type", "status", "laterality", "site", "is_voided")
    search_fields = ("patient__registry_code", "patient__last_name")
    date_hierarchy = "created_on"
    inlines = [CatheterDetailInline, MaturationAssessmentInline,
               AccessProcedureInline, AccessComplicationInline]
    fieldsets = (
        (None, {
            "fields": ("patient", "access_type", "laterality", "site", "plan",
                       "graft_material", "status", "notes"),
        }),
        ("Pathway milestones", {
            "fields": ("created_on", "maturation_confirmed_on", "first_cannulation_on",
                       "first_successful_cannulation_on",
                       "dialysis_use_confirmed_by", "dialysis_use_confirmed_on"),
        }),
        ("End of use", {
            "fields": ("abandoned_on", "abandonment_reason", "removed_on", "removal_reason"),
        }),
    )


class ProcedureDeviceInline(admin.TabularInline):
    model = ProcedureDevice
    extra = 0


@admin.register(AccessProcedure)
class AccessProcedureAdmin(admin.ModelAdmin):
    list_display = ("access", "procedure_type", "performed_on", "operator",
                    "urgency", "technical_success")
    list_filter = ("procedure_type", "urgency", "technical_success", "is_voided")
    search_fields = ("access__patient__registry_code", "access__patient__last_name")
    date_hierarchy = "performed_on"
    inlines = [ProcedureDeviceInline]


class InfectionDetailInline(admin.StackedInline):
    model = InfectionDetail
    extra = 0


class ThrombosisDysfunctionDetailInline(admin.StackedInline):
    model = ThrombosisDysfunctionDetail
    extra = 0


@admin.register(AccessComplication)
class AccessComplicationAdmin(admin.ModelAdmin):
    list_display = ("access", "complication_type", "onset_date", "triage_status",
                    "management", "resolved")
    list_filter = ("complication_type", "triage_status", "management", "resolved", "is_voided")
    search_fields = ("access__patient__registry_code", "access__patient__last_name")
    date_hierarchy = "onset_date"
    inlines = [InfectionDetailInline, ThrombosisDysfunctionDetailInline]


@admin.register(MaturationAssessment)
class MaturationAssessmentAdmin(admin.ModelAdmin):
    list_display = ("access", "assessment_date", "assessment_type", "thrill_present",
                    "flow_volume_ml_min", "verdict", "assessed_by")
    list_filter = ("assessment_type", "verdict")
    search_fields = ("access__patient__registry_code", "access__patient__last_name")
    date_hierarchy = "assessment_date"


@admin.register(Device)
class DeviceAdmin(admin.ModelAdmin):
    list_display = ("manufacturer", "model_name", "size_spec", "device_type", "is_active")
    list_filter = ("device_type", "is_active")
    search_fields = ("manufacturer", "model_name")
