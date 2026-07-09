import datetime

from django.db import IntegrityError, transaction
from django.test import TestCase

from .models import Patient, PatientStatus, PatientStatusEvent, Sex


def make_patient(**overrides):
    defaults = {
        "first_name": "Giorgi",
        "last_name": "Beridze",
        "date_of_birth": datetime.date(1958, 3, 14),
        "sex": Sex.MALE,
    }
    defaults.update(overrides)
    return Patient.objects.create(**defaults)


class PatientModelTests(TestCase):
    def test_registry_code_is_generated_and_stable(self):
        patient = make_patient()
        self.assertEqual(patient.registry_code, f"DA-{patient.pk:06d}")
        code = patient.registry_code
        patient.save()
        patient.refresh_from_db()
        self.assertEqual(patient.registry_code, code)

    def test_registry_codes_are_unique_across_patients(self):
        first = make_patient()
        second = make_patient(first_name="Nino")
        self.assertNotEqual(first.registry_code, second.registry_code)

    def test_blank_national_id_does_not_collide(self):
        make_patient()
        make_patient(first_name="Nino")  # both national_id="" — allowed

    def test_duplicate_national_id_rejected(self):
        make_patient(national_id="01001012345")
        with self.assertRaises(IntegrityError), transaction.atomic():
            make_patient(first_name="Nino", national_id="01001012345")


class PatientStatusEventTests(TestCase):
    def test_latest_event_drives_current_status(self):
        patient = make_patient()
        self.assertEqual(patient.current_status, PatientStatus.PREDIALYSIS)

        PatientStatusEvent.objects.create(
            patient=patient,
            status=PatientStatus.ON_HEMODIALYSIS,
            event_date=datetime.date(2026, 1, 10),
        )
        patient.refresh_from_db()
        self.assertEqual(patient.current_status, PatientStatus.ON_HEMODIALYSIS)
        self.assertEqual(patient.current_status_date, datetime.date(2026, 1, 10))

        # A backdated event must not override a later one.
        PatientStatusEvent.objects.create(
            patient=patient,
            status=PatientStatus.PREDIALYSIS,
            event_date=datetime.date(2025, 11, 1),
        )
        patient.refresh_from_db()
        self.assertEqual(patient.current_status, PatientStatus.ON_HEMODIALYSIS)

    def test_deleting_latest_event_recomputes_status(self):
        patient = make_patient()
        PatientStatusEvent.objects.create(
            patient=patient,
            status=PatientStatus.ON_HEMODIALYSIS,
            event_date=datetime.date(2026, 1, 10),
        )
        death = PatientStatusEvent.objects.create(
            patient=patient,
            status=PatientStatus.DECEASED,
            event_date=datetime.date(2026, 3, 1),
        )
        death.delete()
        patient.refresh_from_db()
        self.assertEqual(patient.current_status, PatientStatus.ON_HEMODIALYSIS)
