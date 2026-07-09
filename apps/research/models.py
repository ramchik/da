from django.conf import settings
from django.db import models


class ExportDataset(models.TextChoices):
    PATIENTS = "patients", "Patients (pseudonymized)"
    ACCESSES = "accesses", "Access episodes"
    PROCEDURES = "procedures", "Procedures"
    COMPLICATIONS = "complications", "Complications"
    SESSIONS_AGGREGATE = "sessions_aggregate", "Session aggregates"
    FULL_BUNDLE = "full_bundle", "Full anonymized bundle"


class ExportLog(models.Model):
    """Who exported what, when — mandatory trail for personal-data holders.

    Rows are written by the export view itself, never manually.
    """

    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="export_logs"
    )
    exported_at = models.DateTimeField(auto_now_add=True)
    dataset = models.CharField(max_length=32, choices=ExportDataset.choices)
    filters = models.JSONField(default=dict, blank=True, help_text="Cohort parameters used.")
    row_count = models.PositiveIntegerField()
    file_sha256 = models.CharField(max_length=64, blank=True)

    class Meta:
        ordering = ["-exported_at"]
        indexes = [
            models.Index(fields=["requested_by", "-exported_at"], name="export_user_date_idx"),
        ]

    def __str__(self):
        return f"{self.get_dataset_display()} by {self.requested_by} at {self.exported_at:%Y-%m-%d %H:%M}"
