from django.conf import settings
from django.db import models


class TimeStampedModel(models.Model):
    """Abstract base adding creation/modification timestamps to every record."""

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class VoidableModel(models.Model):
    """Clinical rows are never physically deleted by users.

    "Deleting" sets ``is_voided`` with a reason; every query path must
    filter ``is_voided=False`` by default. The audit trail records the
    void like any other update.
    """

    is_voided = models.BooleanField(default=False)
    void_reason = models.CharField(max_length=255, blank=True)

    class Meta:
        abstract = True


class RegistrySetting(models.Model):
    """Superuser-editable clinical thresholds (product spec §13).

    Reads go through ``RegistrySetting.get(key)`` which falls back to
    ``DEFAULTS`` so the application works before/without seeding.
    """

    key = models.CharField(max_length=64, primary_key=True)
    value = models.JSONField()
    description = models.CharField(max_length=255)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="updated_settings",
    )
    updated_at = models.DateTimeField(auto_now=True)

    # key: (default value, description)
    DEFAULTS = {
        "maturation_deadline_days": (42, "Days after AVF/AVG creation before maturation assessment is overdue"),
        "nonmaturation_decision_days": (84, "Days after creation to declare nonmaturation if still unusable"),
        "early_thrombosis_window_days": (30, "Thrombosis within this window counts as early (fixed for comparability)"),
        "sessions_before_confirmation": (6, "Successful sessions before prompting nephrologist confirmation"),
        "tdc_removal_alert_days": (14, "Days after AVF confirmation before a lingering TDC raises an alert"),
        "temporary_catheter_dwell_alert_days": (14, "Maximum temporary (non-cuffed) catheter dwell before alerting"),
        "session_log_gap_alert_days": (30, "Days without a session log on an in-use access before alerting"),
        "low_qb_alert_threshold_ml_min": (250, "Qb below this on consecutive sessions raises an alert"),
    }

    class Meta:
        ordering = ["key"]

    def __str__(self):
        return f"{self.key} = {self.value}"

    @classmethod
    def get(cls, key):
        try:
            return cls.objects.get(pk=key).value
        except cls.DoesNotExist:
            return cls.DEFAULTS[key][0]
