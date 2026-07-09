from django.apps import AppConfig, apps

# Single authoritative list of clinical models under audit. The audit app
# is last in INSTALLED_APPS so all of these are loaded by the time
# ready() runs.
AUDITED_MODELS = [
    "patients.Patient",
    "patients.PatientStatusEvent",
    "patients.ClinicalNote",
    "vascular_access.VesselMapping",
    "vascular_access.AccessPlan",
    "vascular_access.VascularAccess",
    "vascular_access.AccessProcedure",
    "vascular_access.AccessComplication",
    "dialysis.DialysisSessionLog",
]


class AuditConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.audit"

    def ready(self):
        from .registry import register_audited_model

        for label in AUDITED_MODELS:
            register_audited_model(apps.get_model(label))
