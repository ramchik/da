import datetime

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from apps.patients.tests import make_patient

from .models import (
    AccessComplication,
    AccessProcedure,
    AccessSite,
    AccessType,
    ComplicationType,
    Laterality,
    ProcedureType,
    VascularAccess,
)


def make_access(patient=None, **overrides):
    defaults = {
        "patient": patient or make_patient(),
        "access_type": AccessType.RADIOCEPHALIC_AVF,
        "laterality": Laterality.LEFT,
        "site": AccessSite.FOREARM,
        "created_on": datetime.date(2026, 1, 5),
    }
    defaults.update(overrides)
    return VascularAccess.objects.create(**defaults)


class VascularAccessTests(TestCase):
    def test_category_mapping(self):
        access = make_access()
        self.assertEqual(access.category, "fistula")
        self.assertEqual(
            make_access(patient=access.patient, access_type=AccessType.PROSTHETIC_AVG).category,
            "graft",
        )
        catheter = make_access(
            patient=access.patient,
            access_type=AccessType.TUNNELED_CUFFED_CATHETER,
            site=AccessSite.INTERNAL_JUGULAR,
            laterality=Laterality.RIGHT,
        )
        self.assertEqual(catheter.category, "catheter")
        self.assertTrue(catheter.is_catheter)

    def test_days_to_maturation(self):
        access = make_access(maturation_confirmed_on=datetime.date(2026, 2, 16))
        self.assertEqual(access.days_to_maturation, 42)
        self.assertIsNone(make_access(patient=access.patient).days_to_maturation)

    def test_milestone_dates_cannot_precede_creation(self):
        access = make_access()
        access.abandoned_on = access.created_on - datetime.timedelta(days=1)
        with self.assertRaises(ValidationError):
            access.full_clean()

    def test_only_one_creation_procedure_per_access(self):
        access = make_access()
        AccessProcedure.objects.create(
            access=access,
            procedure_type=ProcedureType.CREATION,
            performed_on=access.created_on,
        )
        with self.assertRaises(IntegrityError), transaction.atomic():
            AccessProcedure.objects.create(
                access=access,
                procedure_type=ProcedureType.CREATION,
                performed_on=access.created_on,
            )
        # Revisions remain unrestricted.
        AccessProcedure.objects.create(
            access=access,
            procedure_type=ProcedureType.ANGIOPLASTY,
            performed_on=access.created_on + datetime.timedelta(days=90),
        )


class AccessComplicationTests(TestCase):
    def test_early_thrombosis_window(self):
        access = make_access()
        early = AccessComplication.objects.create(
            access=access,
            complication_type=ComplicationType.THROMBOSIS,
            onset_date=access.created_on + datetime.timedelta(days=10),
        )
        late = AccessComplication.objects.create(
            access=access,
            complication_type=ComplicationType.THROMBOSIS,
            onset_date=access.created_on + datetime.timedelta(days=200),
        )
        infection = AccessComplication.objects.create(
            access=access,
            complication_type=ComplicationType.CRBSI,
            onset_date=access.created_on + datetime.timedelta(days=5),
        )
        self.assertTrue(early.is_early_thrombosis)
        self.assertFalse(late.is_early_thrombosis)
        self.assertFalse(infection.is_early_thrombosis)
