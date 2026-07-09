from django.db import migrations


def seed_defaults(apps, schema_editor):
    RegistrySetting = apps.get_model("core", "RegistrySetting")
    # Mirror of RegistrySetting.DEFAULTS at the time of this migration;
    # RegistrySetting.get() also falls back to code defaults, so this seed
    # exists purely to make the thresholds visible/editable in the admin.
    defaults = {
        "maturation_deadline_days": (42, "Days after AVF/AVG creation before maturation assessment is overdue"),
        "nonmaturation_decision_days": (84, "Days after creation to declare nonmaturation if still unusable"),
        "early_thrombosis_window_days": (30, "Thrombosis within this window counts as early (fixed for comparability)"),
        "sessions_before_confirmation": (6, "Successful sessions before prompting nephrologist confirmation"),
        "tdc_removal_alert_days": (14, "Days after AVF confirmation before a lingering TDC raises an alert"),
        "temporary_catheter_dwell_alert_days": (14, "Maximum temporary (non-cuffed) catheter dwell before alerting"),
        "session_log_gap_alert_days": (30, "Days without a session log on an in-use access before alerting"),
        "low_qb_alert_threshold_ml_min": (250, "Qb below this on consecutive sessions raises an alert"),
    }
    for key, (value, description) in defaults.items():
        RegistrySetting.objects.get_or_create(
            key=key, defaults={"value": value, "description": description}
        )


def unseed_defaults(apps, schema_editor):
    RegistrySetting = apps.get_model("core", "RegistrySetting")
    RegistrySetting.objects.filter(pk__in=[
        "maturation_deadline_days", "nonmaturation_decision_days",
        "early_thrombosis_window_days", "sessions_before_confirmation",
        "tdc_removal_alert_days", "temporary_catheter_dwell_alert_days",
        "session_log_gap_alert_days", "low_qb_alert_threshold_ml_min",
    ]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed_defaults, unseed_defaults),
    ]
