import datetime

from django.db import IntegrityError, transaction
from django.test import TestCase

from apps.patients.tests import make_patient

from .models import FollowUpTask, TaskStatus, TaskType


def make_task(patient=None, **overrides):
    defaults = {
        "patient": patient or make_patient(),
        "task_type": TaskType.MATURATION_ASSESSMENT,
        "title": "Maturation assessment",
        "due_date": datetime.date.today() + datetime.timedelta(days=42),
    }
    defaults.update(overrides)
    return FollowUpTask.objects.create(**defaults)


class FollowUpTaskTests(TestCase):
    def test_overdue_flag(self):
        yesterday = datetime.date.today() - datetime.timedelta(days=1)
        overdue = make_task(due_date=yesterday)
        self.assertTrue(overdue.is_overdue)

        future = make_task(patient=overdue.patient, due_date=datetime.date.today())
        self.assertFalse(future.is_overdue)

        done = make_task(patient=overdue.patient, due_date=yesterday, status=TaskStatus.DONE)
        self.assertFalse(done.is_overdue)

    def test_patient_has_overdue_follow_up(self):
        patient = make_patient()
        self.assertFalse(patient.has_overdue_follow_up)
        make_task(patient=patient, due_date=datetime.date.today() - datetime.timedelta(days=3))
        self.assertTrue(patient.has_overdue_follow_up)

    def test_dedupe_key_unique_among_open_tasks(self):
        patient = make_patient()
        make_task(patient=patient, dedupe_key="maturation_assessment:access:1")
        with self.assertRaises(IntegrityError), transaction.atomic():
            make_task(patient=patient, dedupe_key="maturation_assessment:access:1")
        # A done task releases the key for a new open task.
        FollowUpTask.objects.filter(dedupe_key="maturation_assessment:access:1").update(
            status=TaskStatus.DONE
        )
        make_task(patient=patient, dedupe_key="maturation_assessment:access:1")

    def test_manual_tasks_without_dedupe_key_can_repeat(self):
        patient = make_patient()
        make_task(patient=patient)
        make_task(patient=patient)  # both open, no key — allowed
