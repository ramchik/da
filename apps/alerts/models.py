from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.core.models import TimeStampedModel
from apps.dialysis.models import DialysisSessionLog
from apps.patients.models import Patient
from apps.vascular_access.models import AccessComplication, VascularAccess


class AlertSeverity(models.TextChoices):
    RED = "red", "Same-day action"
    AMBER = "amber", "This week"
    YELLOW = "yellow", "Housekeeping"


class AlertStatus(models.TextChoices):
    ACTIVE = "active", "Active"
    SNOOZED = "snoozed", "Snoozed"
    RESOLVED = "resolved", "Resolved"


class Alert(TimeStampedModel):
    """Persisted instance of a rule from the spec's alert list (A1–A15).

    The rule *logic* lives in the evaluation layer (page-load queries in
    MVP, nightly job later); this table stores raised instances so
    resolutions, notes and snoozes survive. ``dedupe_key`` guarantees at
    most one live alert per rule+object.
    """

    rule_code = models.CharField(max_length=8, help_text="A1–A15 per product spec §10.")
    severity = models.CharField(max_length=8, choices=AlertSeverity.choices)
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name="alerts")
    access = models.ForeignKey(
        VascularAccess, null=True, blank=True, on_delete=models.CASCADE, related_name="alerts"
    )
    complication = models.ForeignKey(
        AccessComplication, null=True, blank=True, on_delete=models.SET_NULL, related_name="alerts"
    )
    session_log = models.ForeignKey(
        DialysisSessionLog, null=True, blank=True, on_delete=models.SET_NULL, related_name="alerts"
    )
    message = models.CharField(max_length=500)
    status = models.CharField(max_length=16, choices=AlertStatus.choices, default=AlertStatus.ACTIVE)
    first_raised_at = models.DateTimeField(default=timezone.now)
    last_evaluated_at = models.DateTimeField(default=timezone.now)
    snoozed_until = models.DateField(null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="resolved_alerts",
    )
    resolution_note = models.CharField(max_length=500, blank=True)
    dedupe_key = models.CharField(max_length=120)

    class Meta:
        ordering = ["severity", "-first_raised_at"]
        indexes = [
            models.Index(fields=["status", "severity"], name="alert_status_severity_idx"),
            models.Index(fields=["patient"], name="alert_patient_idx"),
        ]
        constraints = [
            # Spec §10: alerts are dismissible only with a note.
            models.CheckConstraint(
                condition=~models.Q(status="resolved") | ~models.Q(resolution_note=""),
                name="alert_resolution_requires_note",
            ),
            models.CheckConstraint(
                condition=~models.Q(status="snoozed") | models.Q(snoozed_until__isnull=False),
                name="alert_snooze_requires_date",
            ),
            models.UniqueConstraint(
                fields=["dedupe_key"],
                condition=models.Q(status__in=["active", "snoozed"]),
                name="unique_live_alert_dedupe_key",
            ),
        ]

    def __str__(self):
        return f"[{self.rule_code}/{self.get_severity_display()}] {self.patient.registry_code}: {self.message[:60]}"
