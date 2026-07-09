from django.conf import settings
from django.core.serializers.json import DjangoJSONEncoder
from django.db import models


class AuditAction(models.TextChoices):
    CREATE = "create", "Create"
    UPDATE = "update", "Update"
    DELETE = "delete", "Delete"


class AuditLog(models.Model):
    """Append-only trail of every change to an audited clinical record.

    Rows are written by signal handlers (see ``apps.audit.registry``) and
    must never be edited or deleted from application code.
    """

    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="audit_entries",
    )
    action = models.CharField(max_length=8, choices=AuditAction.choices)
    model_label = models.CharField(max_length=100, db_index=True, help_text="e.g. patients.Patient")
    object_pk = models.CharField(max_length=64, db_index=True)
    object_repr = models.CharField(max_length=255)
    changes = models.JSONField(
        default=dict,
        blank=True,
        encoder=DjangoJSONEncoder,
        help_text='Per-field diff: {"field": [old, new], …}',
    )

    class Meta:
        ordering = ["-timestamp"]

    def __str__(self):
        return f"{self.get_action_display()} {self.model_label}#{self.object_pk} at {self.timestamp:%Y-%m-%d %H:%M}"
