import datetime

from django.conf import settings
from django.db import models

from apps.accounts.models import Role
from apps.core.models import TimeStampedModel
from apps.patients.models import Patient
from apps.vascular_access.models import AccessComplication, VascularAccess


class TaskType(models.TextChoices):
    PLAN_ACCESS = "plan_access", "Plan vascular access"
    MAPPING_NEEDED = "mapping_needed", "Vascular mapping needed"
    SCHEDULE_CREATION = "schedule_creation", "Schedule creation procedure"
    POSTOP_CHECK = "postop_check", "Post-operative check (~2 weeks)"
    MATURATION_ASSESSMENT = "maturation_assessment", "Maturation assessment"
    INFORM_CENTER_READY = "inform_center_ready", "Inform dialysis center — ready for cannulation"
    FISTULOGRAM_DECISION = "fistulogram_decision", "Fistulogram / intervention decision"
    PLAN_PERMANENT_ACCESS = "plan_permanent_access", "Plan permanent access (catheter-only patient)"
    REMOVE_CATHETER = "remove_catheter", "Remove tunneled catheter"
    TREAT_COMPLICATION = "treat_complication", "Treat / triage complication"
    EARLY_REVIEW = "early_review", "Early review (technical failure)"
    CHASE_SESSION_LOGS = "chase_session_logs", "Chase missing session logs"
    CUSTOM = "custom", "Custom task"


class TaskStatus(models.TextChoices):
    OPEN = "open", "Open"
    DONE = "done", "Done"
    DEFERRED = "deferred", "Deferred"
    CANCELLED = "cancelled", "Cancelled"


class TaskSource(models.TextChoices):
    SYSTEM = "system", "System-generated"
    MANUAL = "manual", "Manually created"


class FollowUpTask(TimeStampedModel):
    """Worklist item driving follow-up (spec workflows W1–W10).

    System rules create tasks with a ``dedupe_key`` so re-evaluating a
    rule can never duplicate an open task; manual tasks leave it empty.
    """

    task_type = models.CharField(max_length=40, choices=TaskType.choices)
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name="follow_up_tasks")
    access = models.ForeignKey(
        VascularAccess, null=True, blank=True, on_delete=models.CASCADE,
        related_name="follow_up_tasks",
    )
    complication = models.ForeignKey(
        AccessComplication, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="follow_up_tasks",
    )
    title = models.CharField(max_length=200)
    details = models.TextField(blank=True)
    due_date = models.DateField()
    assigned_role = models.CharField(max_length=32, choices=Role.choices, blank=True)
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="assigned_tasks",
    )
    status = models.CharField(max_length=16, choices=TaskStatus.choices, default=TaskStatus.OPEN)
    deferred_until = models.DateField(null=True, blank=True)
    deferral_reason = models.CharField(max_length=255, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    completed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="completed_tasks",
    )
    source = models.CharField(max_length=8, choices=TaskSource.choices, default=TaskSource.SYSTEM)
    dedupe_key = models.CharField(max_length=120, null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="created_tasks",
    )

    class Meta:
        ordering = ["due_date", "id"]
        indexes = [
            models.Index(fields=["status", "due_date"], name="task_status_due_idx"),
            models.Index(fields=["assigned_to", "status"], name="task_assignee_status_idx"),
            models.Index(fields=["patient"], name="task_patient_idx"),
        ]
        constraints = [
            # A deferral without a date and reason is just an ignored task.
            models.CheckConstraint(
                condition=~models.Q(status="deferred")
                | (models.Q(deferred_until__isnull=False) & ~models.Q(deferral_reason="")),
                name="task_deferral_requires_date_and_reason",
            ),
            models.UniqueConstraint(
                fields=["dedupe_key"],
                condition=models.Q(status="open", dedupe_key__isnull=False),
                name="unique_open_task_dedupe_key",
            ),
        ]

    def __str__(self):
        return f"[{self.get_status_display()}] {self.title} — {self.patient.registry_code} (due {self.due_date})"

    @property
    def is_overdue(self):
        """Open task past its due date (worklist flag + alert A14 input)."""
        return self.status == TaskStatus.OPEN and self.due_date < datetime.date.today()
