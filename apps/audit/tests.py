import datetime

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.accounts.models import Role
from apps.patients.models import Patient
from apps.patients.tests import make_patient

from .middleware import set_current_actor
from .models import AuditAction, AuditLog


class AuditTrailTests(TestCase):
    def tearDown(self):
        set_current_actor(None)

    def entries_for(self, patient):
        return AuditLog.objects.filter(
            model_label="patients.Patient", object_pk=str(patient.pk)
        ).order_by("timestamp", "id")

    def test_create_is_logged_with_snapshot(self):
        patient = make_patient()
        create_entry = self.entries_for(patient).filter(action=AuditAction.CREATE).get()
        self.assertEqual(create_entry.changes["last_name"], "Beridze")

    def test_update_logs_only_changed_fields(self):
        patient = make_patient()
        AuditLog.objects.all().delete()

        patient.phone = "+995 555 123456"
        patient.save()

        entry = self.entries_for(patient).get()
        self.assertEqual(entry.action, AuditAction.UPDATE)
        self.assertEqual(entry.changes, {"phone": ["", "+995 555 123456"]})

    def test_noop_save_writes_nothing(self):
        patient = make_patient()
        AuditLog.objects.all().delete()
        patient.save()
        self.assertEqual(self.entries_for(patient).count(), 0)

    def test_delete_is_logged(self):
        patient = make_patient()
        pk = patient.pk
        patient.delete()
        entry = AuditLog.objects.filter(
            model_label="patients.Patient", object_pk=str(pk), action=AuditAction.DELETE
        ).get()
        self.assertEqual(entry.changes["first_name"], "Giorgi")

    def test_actor_is_attributed(self):
        surgeon = get_user_model().objects.create_user(
            username="surgeon", password="x", role=Role.VASCULAR_SURGEON
        )
        set_current_actor(surgeon)
        patient = make_patient()
        entry = self.entries_for(patient).filter(action=AuditAction.CREATE).get()
        self.assertEqual(entry.actor, surgeon)

    def test_date_fields_survive_json_serialization(self):
        patient = make_patient()
        AuditLog.objects.all().delete()
        patient.referral_date = datetime.date(2026, 6, 1)
        patient.save()
        entry = self.entries_for(patient).get()
        entry.refresh_from_db()
        self.assertEqual(entry.changes["referral_date"], [None, "2026-06-01"])

    def test_users_themselves_are_not_audited(self):
        get_user_model().objects.create_user(username="nurse", password="x", role=Role.DIALYSIS_NURSE)
        self.assertFalse(AuditLog.objects.filter(model_label="accounts.User").exists())
