from django.conf import settings
from django.core.validators import RegexValidator
from django.db import models, transaction

from apps.core.models import TimeStampedModel


class Sex(models.TextChoices):
    MALE = "male", "Male"
    FEMALE = "female", "Female"


class CKDStage(models.TextChoices):
    """CKD stage at referral to the vascular access service."""

    STAGE_4 = "stage_4", "CKD stage 4 (predialysis)"
    STAGE_5 = "stage_5", "CKD stage 5 (predialysis)"
    STAGE_5D = "stage_5d", "CKD stage 5D (already on dialysis)"


class PrimaryRenalDisease(models.TextChoices):
    DIABETIC_NEPHROPATHY = "diabetic_nephropathy", "Diabetic nephropathy"
    HYPERTENSIVE_NEPHROPATHY = "hypertensive_nephropathy", "Hypertensive nephropathy"
    GLOMERULONEPHRITIS = "glomerulonephritis", "Glomerulonephritis"
    POLYCYSTIC_KIDNEY_DISEASE = "polycystic_kidney_disease", "Polycystic kidney disease"
    OBSTRUCTIVE_UROPATHY = "obstructive_uropathy", "Obstructive uropathy"
    INTERSTITIAL_NEPHRITIS = "interstitial_nephritis", "Interstitial nephritis"
    OTHER = "other", "Other"
    UNKNOWN = "unknown", "Unknown"


class PatientStatus(models.TextChoices):
    """Where the patient currently is on the dialysis access pathway."""

    PREDIALYSIS = "predialysis", "CKD 4–5, predialysis"
    ON_HEMODIALYSIS = "on_hemodialysis", "On hemodialysis"
    TRANSPLANTED = "transplanted", "Kidney transplant recipient"
    TRANSFERRED_OUT = "transferred_out", "Transferred to another center"
    LOST_TO_FOLLOW_UP = "lost_to_follow_up", "Lost to follow-up"
    DECEASED = "deceased", "Deceased"


class Patient(TimeStampedModel):
    """One row per person followed by the access service.

    Personal identifiers live only on this model; every downstream
    clinical table references the patient by foreign key, so research
    exports can substitute ``registry_code`` for identity.
    """

    registry_code = models.CharField(
        max_length=16,
        unique=True,
        editable=False,
        help_text="Stable pseudonymous identifier used in exports (e.g. DA-000042).",
    )
    national_id = models.CharField(
        max_length=11,
        blank=True,
        validators=[RegexValidator(r"^\d{11}$", "Georgian personal number is 11 digits.")],
        help_text="Georgian personal number (piradi nomeri), if known.",
    )
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    date_of_birth = models.DateField()
    sex = models.CharField(max_length=8, choices=Sex.choices)
    phone = models.CharField(max_length=32, blank=True)
    region = models.CharField(max_length=100, blank=True, help_text="Region / city of residence.")
    address = models.CharField(max_length=255, blank=True)
    dialysis_center = models.CharField(
        max_length=255, blank=True, help_text="Dialysis center the patient attends, if on HD."
    )

    # Referral into the access pathway
    referral_date = models.DateField(
        null=True, blank=True, help_text="Date referred to the vascular access service."
    )
    ckd_stage_at_referral = models.CharField(
        max_length=16, choices=CKDStage.choices, blank=True
    )
    primary_renal_disease = models.CharField(
        max_length=32, choices=PrimaryRenalDisease.choices, default=PrimaryRenalDisease.UNKNOWN
    )
    dialysis_start_date = models.DateField(null=True, blank=True)
    responsible_nephrologist = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="nephrology_patients",
        limit_choices_to={"role": "nephrologist"},
    )
    responsible_surgeon = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="surgical_patients",
        limit_choices_to={"role": "vascular_surgeon"},
    )

    # Comorbidities relevant to access planning and outcomes
    has_diabetes = models.BooleanField(default=False)
    has_hypertension = models.BooleanField(default=False)
    has_coronary_artery_disease = models.BooleanField(default=False)
    has_heart_failure = models.BooleanField(default=False)
    has_peripheral_arterial_disease = models.BooleanField(default=False)
    has_previous_central_venous_catheter = models.BooleanField(
        default=False, help_text="Any prior central venous catheter (risk of central stenosis)."
    )
    on_anticoagulation_or_antiplatelet = models.BooleanField(default=False)
    comorbidity_notes = models.TextField(blank=True)

    # Denormalized from the latest PatientStatusEvent for cheap filtering;
    # PatientStatusEvent rows remain the source of truth.
    current_status = models.CharField(
        max_length=32, choices=PatientStatus.choices, default=PatientStatus.PREDIALYSIS
    )
    current_status_date = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ["last_name", "first_name"]
        constraints = [
            models.UniqueConstraint(
                fields=["national_id"],
                condition=~models.Q(national_id=""),
                name="unique_national_id_when_present",
            ),
        ]

    def __str__(self):
        return f"{self.registry_code} — {self.last_name} {self.first_name}"

    def save(self, *args, **kwargs):
        # The registry code derives from the primary key, so a new row is
        # inserted first and stamped in the same transaction.
        with transaction.atomic():
            super().save(*args, **kwargs)
            if not self.registry_code:
                self.registry_code = f"DA-{self.pk:06d}"
                super().save(update_fields=["registry_code"])

    @property
    def full_name(self):
        return f"{self.last_name} {self.first_name}"

    def refresh_current_status(self):
        """Re-derive the denormalized status from the event history."""
        latest = self.status_events.order_by("-event_date", "-id").first()
        if latest is None:
            return
        if (
            self.current_status != latest.status
            or self.current_status_date != latest.event_date
        ):
            self.current_status = latest.status
            self.current_status_date = latest.event_date
            self.save(update_fields=["current_status", "current_status_date", "updated_at"])


class PatientStatusEvent(TimeStampedModel):
    """History of pathway transitions: predialysis → HD → transplant/death/…

    Statuses can recur (e.g. failed transplant returning to hemodialysis),
    so this is an append-only log rather than one row per status.
    """

    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name="status_events")
    status = models.CharField(max_length=32, choices=PatientStatus.choices)
    event_date = models.DateField()
    details = models.CharField(
        max_length=255,
        blank=True,
        help_text="Cause of death, destination center, transplant details, etc.",
    )
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="recorded_status_events",
    )

    class Meta:
        ordering = ["-event_date", "-id"]

    def __str__(self):
        return f"{self.patient.registry_code}: {self.get_status_display()} on {self.event_date}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self.patient.refresh_current_status()

    def delete(self, *args, **kwargs):
        patient = self.patient
        super().delete(*args, **kwargs)
        patient.refresh_current_status()


class ClinicalNote(TimeStampedModel):
    """Free-text commentary on a patient (e.g. nephrologist remarks)."""

    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name="clinical_notes")
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="clinical_notes"
    )
    body = models.TextField()

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Note on {self.patient.registry_code} by {self.author or 'unknown'}"
