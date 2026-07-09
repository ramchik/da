from django.test import TestCase

from .models import RegistrySetting


class RegistrySettingTests(TestCase):
    def test_seeded_defaults_are_readable(self):
        # The seed migration ran during test DB setup.
        self.assertEqual(RegistrySetting.get("maturation_deadline_days"), 42)

    def test_overridden_value_wins(self):
        RegistrySetting.objects.filter(pk="maturation_deadline_days").update(value=56)
        self.assertEqual(RegistrySetting.get("maturation_deadline_days"), 56)

    def test_missing_row_falls_back_to_code_default(self):
        RegistrySetting.objects.all().delete()
        self.assertEqual(RegistrySetting.get("sessions_before_confirmation"), 6)
