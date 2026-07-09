from django.contrib import admin

from .models import ClinicalNote, Patient, PatientStatusEvent


class PatientStatusEventInline(admin.TabularInline):
    model = PatientStatusEvent
    extra = 0
    fields = ("status", "event_date", "details", "recorded_by")


class ClinicalNoteInline(admin.TabularInline):
    model = ClinicalNote
    extra = 0
    fields = ("author", "body", "created_at")
    readonly_fields = ("created_at",)


@admin.register(Patient)
class PatientAdmin(admin.ModelAdmin):
    list_display = (
        "registry_code",
        "last_name",
        "first_name",
        "date_of_birth",
        "sex",
        "ckd_stage_at_referral",
        "current_status",
        "dialysis_center",
    )
    list_filter = ("current_status", "ckd_stage_at_referral", "primary_renal_disease", "sex")
    search_fields = ("registry_code", "last_name", "first_name", "national_id", "phone")
    readonly_fields = ("registry_code", "current_status", "current_status_date")
    date_hierarchy = "referral_date"
    inlines = [PatientStatusEventInline, ClinicalNoteInline]
    fieldsets = (
        ("Identity", {
            "fields": (
                "registry_code", "national_id", "first_name", "last_name",
                "date_of_birth", "sex", "phone", "region", "address",
            ),
        }),
        ("Referral & renal history", {
            "fields": (
                "referral_date", "ckd_stage_at_referral", "primary_renal_disease",
                "dialysis_start_date", "dialysis_center",
                "responsible_nephrologist", "responsible_surgeon",
            ),
        }),
        ("Comorbidities", {
            "fields": (
                "has_diabetes", "has_hypertension", "has_coronary_artery_disease",
                "has_heart_failure", "has_peripheral_arterial_disease",
                "has_previous_central_venous_catheter",
                "on_anticoagulation_or_antiplatelet", "comorbidity_notes",
            ),
        }),
        ("Pathway status (derived from status events)", {
            "fields": ("current_status", "current_status_date"),
        }),
    )


@admin.register(PatientStatusEvent)
class PatientStatusEventAdmin(admin.ModelAdmin):
    list_display = ("patient", "status", "event_date", "recorded_by")
    list_filter = ("status",)
    search_fields = ("patient__registry_code", "patient__last_name")
    date_hierarchy = "event_date"


@admin.register(ClinicalNote)
class ClinicalNoteAdmin(admin.ModelAdmin):
    list_display = ("patient", "author", "created_at")
    search_fields = ("patient__registry_code", "patient__last_name", "body")
