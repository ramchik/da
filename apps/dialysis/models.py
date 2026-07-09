from django.conf import settings
from django.db import models

from apps.core.models import TimeStampedModel, VoidableModel
from apps.patients.models import DialysisCenter
from apps.vascular_access.models import VascularAccess


class SessionProblem(models.TextChoices):
    NONE = "none", "No problem"
    DIFFICULT_CANNULATION = "difficult_cannulation", "Difficult cannulation"
    FAILED_CANNULATION = "failed_cannulation", "Failed cannulation"
    INFILTRATION_HEMATOMA = "infiltration_hematoma", "Infiltration / hematoma"
    LOW_BLOOD_FLOW = "low_blood_flow", "Low blood flow"
    HIGH_VENOUS_PRESSURE = "high_venous_pressure", "High venous pressure"
    HIGH_NEGATIVE_ARTERIAL_PRESSURE = "high_negative_arterial_pressure", "High negative arterial pressure"
    PROLONGED_BLEEDING = "prolonged_bleeding", "Prolonged post-dialysis bleeding"
    PAIN = "pain", "Pain during session"
    CATHETER_FLOW_PROBLEM = "catheter_flow_problem", "Catheter flow problem"
    SUSPECTED_INFECTION = "suspected_infection", "Suspected access infection"
    OTHER = "other", "Other"


class DialysisSessionLog(VoidableModel, TimeStampedModel):
    """Per-session functionality record entered by the dialysis nurse.

    This is deliberately lightweight — one row per session (or per
    problematic session) is enough to document first cannulation,
    sustained functionality and early warning signs of dysfunction.
    """

    access = models.ForeignKey(
        VascularAccess, on_delete=models.CASCADE, related_name="dialysis_logs"
    )
    session_date = models.DateField()
    dialysis_center = models.ForeignKey(
        DialysisCenter,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="session_logs",
        help_text="Where the session happened; defaults to the patient's center.",
    )
    cannulation_successful = models.BooleanField(
        null=True, blank=True, help_text="For fistula/graft sessions; leave empty for catheters."
    )
    needle_gauge = models.PositiveSmallIntegerField(null=True, blank=True)
    blood_flow_rate_ml_min = models.PositiveSmallIntegerField(
        null=True, blank=True, help_text="Achieved pump speed (Qb), mL/min."
    )
    arterial_pressure_mmhg = models.SmallIntegerField(null=True, blank=True)
    venous_pressure_mmhg = models.SmallIntegerField(null=True, blank=True)
    problem = models.CharField(
        max_length=40, choices=SessionProblem.choices, default=SessionProblem.NONE
    )
    session_completed = models.BooleanField(default=True)
    notes = models.TextField(blank=True)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="dialysis_logs",
    )

    class Meta:
        ordering = ["-session_date", "-id"]
        verbose_name = "dialysis session log"
        indexes = [
            models.Index(fields=["access", "-session_date"], name="session_access_date_idx"),
            # A7 alert scans only problem sessions.
            models.Index(
                fields=["problem"],
                name="session_problem_idx",
                condition=~models.Q(problem="none"),
            ),
        ]

    def __str__(self):
        return f"Session {self.session_date} on {self.access}"

    @property
    def patient(self):
        return self.access.patient
