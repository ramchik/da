"""Signal-based audit trail.

Models listed in ``apps.audit.apps.AUDITED_MODELS`` get create/update/
delete rows in ``AuditLog`` automatically, with a per-field diff and the
acting user (taken from ``AuditActorMiddleware``'s thread-local).
"""

from django.db.models.signals import post_delete, post_save, pre_save

from .middleware import get_current_actor
from .models import AuditAction, AuditLog

# Bookkeeping fields whose changes carry no clinical meaning.
EXCLUDED_FIELDS = {"created_at", "updated_at", "password", "last_login"}


def _snapshot(instance):
    """Plain dict of concrete field values (FKs as their raw ids)."""
    data = {}
    for field in instance._meta.concrete_fields:
        if field.name in EXCLUDED_FIELDS:
            continue
        data[field.name] = field.value_from_object(instance)
    return data


def _capture_pre_state(sender, instance, **kwargs):
    if instance.pk:
        try:
            instance._audit_pre = _snapshot(sender._default_manager.get(pk=instance.pk))
        except sender.DoesNotExist:
            instance._audit_pre = None
    else:
        instance._audit_pre = None


def _write(instance, action, changes):
    AuditLog.objects.create(
        actor=get_current_actor(),
        action=action,
        model_label=instance._meta.label,
        object_pk=str(instance.pk),
        object_repr=str(instance)[:255],
        changes=changes,
    )


def _log_save(sender, instance, created, **kwargs):
    current = _snapshot(instance)
    if created:
        _write(instance, AuditAction.CREATE, current)
        return
    pre = getattr(instance, "_audit_pre", None) or {}
    diff = {name: [pre.get(name), value] for name, value in current.items() if pre.get(name) != value}
    if diff:
        _write(instance, AuditAction.UPDATE, diff)


def _log_delete(sender, instance, **kwargs):
    _write(instance, AuditAction.DELETE, _snapshot(instance))


def register_audited_model(model):
    uid = f"audit:{model._meta.label_lower}"
    pre_save.connect(_capture_pre_state, sender=model, dispatch_uid=f"{uid}:pre_save")
    post_save.connect(_log_save, sender=model, dispatch_uid=f"{uid}:post_save")
    post_delete.connect(_log_delete, sender=model, dispatch_uid=f"{uid}:post_delete")
