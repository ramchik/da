import datetime

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from apps.patients.tests import make_patient

from .models import (
    AccessComplication,
    AccessProcedure,
    AccessSite,
    AccessStatus,
    AccessType,
    CatheterDetail,
    ComplicationType,
    InfectionDetail,
    Laterality,
    ProcedureType,
    ReasonForCatheter,
    ThrombosisDysfunctionDetail,
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


class CalculatedPropertyTests(TestCase):
    def make_catheter(self, **overrides):
        defaults = {
            "access_type": AccessType.TUNNELED_CUFFED_CATHETER,
            "site": AccessSite.INTERNAL_JUGULAR,
            "laterality": Laterality.RIGHT,
            "status": AccessStatus.IN_USE,
        }
        defaults.update(overrides)
        return make_access(**defaults)

    def test_catheter_days_running_and_stopped(self):
        inserted = datetime.date.today() - datetime.timedelta(days=40)
        catheter = self.make_catheter(created_on=inserted)
        self.assertEqual(catheter.catheter_days, 40)  # clock still running

        catheter.removed_on = inserted + datetime.timedelta(days=25)
        self.assertEqual(catheter.catheter_days, 25)  # clock stopped at removal

        fistula = make_access(patient=catheter.patient)
        self.assertIsNone(fistula.catheter_days)

    def test_catheter_over_90_days_flag(self):
        old = self.make_catheter(created_on=datetime.date.today() - datetime.timedelta(days=120))
        recent = self.make_catheter(
            patient=old.patient, created_on=datetime.date.today() - datetime.timedelta(days=30)
        )
        self.assertTrue(old.catheter_over_90_days)
        self.assertFalse(recent.catheter_over_90_days)

    def test_days_to_first_cannulation_and_abandonment(self):
        access = make_access(
            first_cannulation_on=datetime.date(2026, 2, 20),
            abandoned_on=datetime.date(2026, 9, 1),
            abandonment_reason="thrombosis",
            status=AccessStatus.ABANDONED,
        )
        self.assertEqual(access.days_to_first_cannulation, 46)
        self.assertEqual(access.days_to_abandonment, 239)
        fresh = make_access(patient=access.patient)
        self.assertIsNone(fresh.days_to_first_cannulation)
        self.assertIsNone(fresh.days_to_abandonment)

    def test_is_active_and_patient_active_accesses(self):
        access = make_access()
        self.assertTrue(access.is_active)
        abandoned = make_access(
            patient=access.patient,
            status=AccessStatus.ABANDONED,
            abandoned_on=datetime.date(2026, 3, 1),
            abandonment_reason="nonmaturation",
        )
        self.assertFalse(abandoned.is_active)
        self.assertEqual(list(access.patient.active_accesses), [access])

    def test_catheter_never_maturing(self):
        catheter = self.make_catheter()
        catheter.status = AccessStatus.MATURING
        with self.assertRaises(ValidationError):
            catheter.full_clean()


class DetailTableValidationTests(TestCase):
    def test_catheter_detail_rejects_fistula(self):
        fistula = make_access()
        detail = CatheterDetail(access=fistula, reason_for_catheter=ReasonForCatheter.URGENT_START)
        with self.assertRaises(ValidationError):
            detail.full_clean()

    def test_catheter_detail_accepts_catheter(self):
        catheter = make_access(
            access_type=AccessType.TUNNELED_CUFFED_CATHETER,
            site=AccessSite.INTERNAL_JUGULAR,
            laterality=Laterality.RIGHT,
            status=AccessStatus.IN_USE,
        )
        detail = CatheterDetail(
            access=catheter, reason_for_catheter=ReasonForCatheter.BRIDGE_AVF_MATURING, lumen_count=2
        )
        detail.full_clean()
        detail.save()

    def test_infection_detail_requires_infection_type(self):
        access = make_access()
        thrombosis = AccessComplication.objects.create(
            access=access,
            complication_type=ComplicationType.THROMBOSIS,
            onset_date=access.created_on + datetime.timedelta(days=10),
        )
        with self.assertRaises(ValidationError):
            InfectionDetail(complication=thrombosis).full_clean()
        # And the thrombosis detail attaches fine to the same row.
        ThrombosisDysfunctionDetail(complication=thrombosis).full_clean()

    def test_thrombosis_detail_rejects_infection(self):
        access = make_access()
        crbsi = AccessComplication.objects.create(
            access=access,
            complication_type=ComplicationType.CRBSI,
            onset_date=access.created_on + datetime.timedelta(days=5),
        )
        with self.assertRaises(ValidationError):
            ThrombosisDysfunctionDetail(complication=crbsi).full_clean()
        InfectionDetail(complication=crbsi, organism="S. aureus").full_clean()


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
