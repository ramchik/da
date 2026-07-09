import datetime

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from apps.core.models import TimeStampedModel
from apps.patients.models import Patient

# Thrombosis within this many days of creation counts as "early thrombosis"
# in outcome reports (KDOQI-style early failure window).
EARLY_THROMBOSIS_WINDOW_DAYS = 30


class Laterality(models.TextChoices):
    LEFT = "left", "Left"
    RIGHT = "right", "Right"
    NOT_APPLICABLE = "n_a", "Not applicable"


class AccessType(models.TextChoices):
    RADIOCEPHALIC_AVF = "radiocephalic_avf", "Radiocephalic AVF"
    BRACHIOCEPHALIC_AVF = "brachiocephalic_avf", "Brachiocephalic AVF"
    BRACHIOBASILIC_AVF = "brachiobasilic_avf", "Brachiobasilic AVF"
    TRANSPOSED_BASILIC_AVF = "transposed_basilic_avf", "Transposed basilic AVF"
    PROSTHETIC_AVG = "prosthetic_avg", "Prosthetic AVG"
    TUNNELED_CUFFED_CATHETER = "tunneled_cuffed_catheter", "Tunneled cuffed dialysis catheter"
    TEMPORARY_CATHETER = "temporary_catheter", "Temporary dialysis catheter"
    HERO_GRAFT = "hero_graft", "HeRO graft"
    COMPLEX_ACCESS = "complex_access", "Complex access"


FISTULA_TYPES = {
    AccessType.RADIOCEPHALIC_AVF,
    AccessType.BRACHIOCEPHALIC_AVF,
    AccessType.BRACHIOBASILIC_AVF,
    AccessType.TRANSPOSED_BASILIC_AVF,
}
GRAFT_TYPES = {AccessType.PROSTHETIC_AVG, AccessType.HERO_GRAFT}
CATHETER_TYPES = {AccessType.TUNNELED_CUFFED_CATHETER, AccessType.TEMPORARY_CATHETER}


class AccessSite(models.TextChoices):
    # Fistula / graft sites
    FOREARM = "forearm", "Forearm"
    UPPER_ARM = "upper_arm", "Upper arm"
    THIGH = "thigh", "Thigh"
    CHEST_WALL = "chest_wall", "Chest wall"
    # Catheter insertion sites
    INTERNAL_JUGULAR = "internal_jugular", "Internal jugular vein"
    SUBCLAVIAN = "subclavian", "Subclavian vein"
    FEMORAL = "femoral", "Femoral vein"
    OTHER = "other", "Other"


class VesselMapping(TimeStampedModel):
    """Preoperative duplex ultrasound vascular mapping (one row per exam)."""

    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name="vessel_mappings")
    exam_date = models.DateField()
    side = models.CharField(max_length=8, choices=Laterality.choices)
    cephalic_vein_diameter_mm = models.DecimalField(
        max_digits=4, decimal_places=1, null=True, blank=True
    )
    basilic_vein_diameter_mm = models.DecimalField(
        max_digits=4, decimal_places=1, null=True, blank=True
    )
    radial_artery_diameter_mm = models.DecimalField(
        max_digits=4, decimal_places=1, null=True, blank=True
    )
    brachial_artery_diameter_mm = models.DecimalField(
        max_digits=4, decimal_places=1, null=True, blank=True
    )
    arterial_calcification = models.BooleanField(default=False)
    central_vein_patency_concern = models.BooleanField(
        default=False, help_text="Suspected or documented central venous stenosis/occlusion."
    )
    findings = models.TextField(blank=True)
    performed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="vessel_mappings",
    )

    class Meta:
        ordering = ["-exam_date"]
        verbose_name = "vessel mapping"

    def __str__(self):
        return f"Mapping {self.patient.registry_code} {self.get_side_display()} {self.exam_date}"


class AccessPlan(TimeStampedModel):
    """Documented access strategy decided at planning, before creation."""

    class PlanStatus(models.TextChoices):
        PLANNED = "planned", "Planned"
        PERFORMED = "performed", "Performed"
        CANCELLED = "cancelled", "Cancelled"

    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name="access_plans")
    plan_date = models.DateField()
    planned_access_type = models.CharField(max_length=32, choices=AccessType.choices)
    planned_side = models.CharField(max_length=8, choices=Laterality.choices)
    based_on_mapping = models.ForeignKey(
        VesselMapping, null=True, blank=True, on_delete=models.SET_NULL, related_name="plans"
    )
    planned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="access_plans",
    )
    status = models.CharField(max_length=16, choices=PlanStatus.choices, default=PlanStatus.PLANNED)
    rationale = models.TextField(blank=True)

    class Meta:
        ordering = ["-plan_date"]

    def __str__(self):
        return (
            f"Plan {self.patient.registry_code}: {self.get_planned_access_type_display()}"
            f" ({self.get_planned_side_display()}) on {self.plan_date}"
        )


class AccessStatus(models.TextChoices):
    """Lifecycle of one access, from creation to end of use."""

    MATURING = "maturing", "Created, maturing"
    READY = "ready", "Mature, awaiting first cannulation"
    IN_USE = "in_use", "In use for dialysis"
    FAILED_MATURATION = "failed_maturation", "Never matured (nonmaturation)"
    ABANDONED = "abandoned", "Abandoned"
    REMOVED = "removed", "Removed"


class AbandonmentReason(models.TextChoices):
    NONMATURATION = "nonmaturation", "Nonmaturation"
    THROMBOSIS = "thrombosis", "Thrombosis"
    INFECTION = "infection", "Infection"
    STEAL_SYNDROME = "steal_syndrome", "Steal syndrome / ischemia"
    ANEURYSM = "aneurysm", "Aneurysm / pseudoaneurysm"
    CENTRAL_VEIN_STENOSIS = "central_vein_stenosis", "Central vein stenosis"
    CATHETER_DYSFUNCTION = "catheter_dysfunction", "Catheter dysfunction"
    NO_LONGER_NEEDED = "no_longer_needed", "No longer needed (working access / transplant)"
    PATIENT_DEATH = "patient_death", "Patient death"
    PATIENT_CHOICE = "patient_choice", "Patient choice"
    OTHER = "other", "Other"


class VascularAccess(TimeStampedModel):
    """One dialysis access (fistula, graft or catheter) of one patient.

    Creation and every subsequent intervention are ``AccessProcedure``
    rows; adverse events are ``AccessComplication`` rows. The milestone
    dates stored here anchor the outcome definitions:

    - primary patency: creation → first post-creation intervention or
      thrombosis (computed from procedures/complications);
    - assisted primary patency: creation → first thrombosis;
    - secondary patency: creation → abandonment (``abandoned_on``);
    - time to maturation: ``created_on`` → ``maturation_confirmed_on``;
    - catheter dwell time: ``created_on`` → ``removed_on``.
    """

    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name="accesses")
    access_type = models.CharField(max_length=32, choices=AccessType.choices)
    laterality = models.CharField(max_length=8, choices=Laterality.choices)
    site = models.CharField(max_length=32, choices=AccessSite.choices)
    plan = models.ForeignKey(
        AccessPlan, null=True, blank=True, on_delete=models.SET_NULL, related_name="accesses"
    )
    graft_material = models.CharField(
        max_length=100, blank=True, help_text="For AVG/HeRO: prosthetic material and caliber."
    )
    status = models.CharField(
        max_length=32, choices=AccessStatus.choices, default=AccessStatus.MATURING
    )

    # Milestones along the pathway
    created_on = models.DateField(help_text="Date of the creation/insertion procedure.")
    maturation_confirmed_on = models.DateField(
        null=True, blank=True, help_text="Date maturity was confirmed clinically or on ultrasound."
    )
    first_cannulation_on = models.DateField(null=True, blank=True)
    first_successful_cannulation_on = models.DateField(
        null=True,
        blank=True,
        help_text="First cannulation that delivered an adequate dialysis session.",
    )
    dialysis_use_confirmed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="confirmed_accesses",
        limit_choices_to={"role": "nephrologist"},
        help_text="Nephrologist confirming the access is functioning for dialysis.",
    )
    dialysis_use_confirmed_on = models.DateField(null=True, blank=True)

    # End of life of the access
    abandoned_on = models.DateField(null=True, blank=True)
    abandonment_reason = models.CharField(
        max_length=32, choices=AbandonmentReason.choices, blank=True
    )
    removed_on = models.DateField(
        null=True, blank=True, help_text="Removal/ligation date (mainly catheters)."
    )
    removal_reason = models.CharField(
        max_length=32, choices=AbandonmentReason.choices, blank=True
    )
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_on"]
        verbose_name = "vascular access"
        verbose_name_plural = "vascular accesses"

    def __str__(self):
        return (
            f"{self.patient.registry_code}: {self.get_access_type_display()}"
            f" ({self.get_laterality_display()}) {self.created_on}"
        )

    def clean(self):
        errors = {}
        if self.abandoned_on and self.abandoned_on < self.created_on:
            errors["abandoned_on"] = "Abandonment cannot precede creation."
        if self.removed_on and self.removed_on < self.created_on:
            errors["removed_on"] = "Removal cannot precede creation."
        if self.first_cannulation_on and self.first_cannulation_on < self.created_on:
            errors["first_cannulation_on"] = "First cannulation cannot precede creation."
        if errors:
            raise ValidationError(errors)

    @property
    def category(self):
        """Coarse grouping used in dashboards: fistula / graft / catheter / complex."""
        if self.access_type in FISTULA_TYPES:
            return "fistula"
        if self.access_type in GRAFT_TYPES:
            return "graft"
        if self.access_type in CATHETER_TYPES:
            return "catheter"
        return "complex"

    @property
    def is_catheter(self):
        return self.access_type in CATHETER_TYPES

    @property
    def days_to_maturation(self):
        if self.maturation_confirmed_on is None:
            return None
        return (self.maturation_confirmed_on - self.created_on).days

    @property
    def end_of_use_date(self):
        """Date the access permanently stopped being usable, if it has."""
        return self.abandoned_on or self.removed_on


class ProcedureType(models.TextChoices):
    CREATION = "creation", "Access creation / catheter insertion"
    SECOND_STAGE_TRANSPOSITION = "second_stage_transposition", "Second-stage transposition / superficialization"
    ANGIOPLASTY = "angioplasty", "Percutaneous angioplasty"
    STENT = "stent", "Stent placement"
    SURGICAL_REVISION = "surgical_revision", "Open surgical revision"
    THROMBECTOMY_SURGICAL = "thrombectomy_surgical", "Surgical thrombectomy"
    THROMBECTOMY_ENDOVASCULAR = "thrombectomy_endovascular", "Endovascular thrombectomy / thrombolysis"
    ANEURYSM_REPAIR = "aneurysm_repair", "Aneurysm / pseudoaneurysm repair"
    BANDING_FLOW_REDUCTION = "banding_flow_reduction", "Banding / flow reduction"
    DRIL_OR_ISCHEMIA_PROCEDURE = "dril_or_ischemia_procedure", "DRIL / ischemia-correcting procedure"
    LIGATION = "ligation", "Ligation"
    CATHETER_EXCHANGE = "catheter_exchange", "Catheter exchange over wire"
    CATHETER_REPOSITION = "catheter_reposition", "Catheter repositioning"
    CATHETER_REMOVAL = "catheter_removal", "Catheter removal"
    OTHER = "other", "Other"


class Anesthesia(models.TextChoices):
    LOCAL = "local", "Local"
    REGIONAL_BLOCK = "regional_block", "Regional block"
    SEDATION = "sedation", "Sedation"
    GENERAL = "general", "General"


class AccessProcedure(TimeStampedModel):
    """Every operation on an access: the index creation and all revisions.

    The index creation carries ``procedure_type=CREATION``; any later row
    on the same access ends its primary patency interval.
    """

    class Urgency(models.TextChoices):
        ELECTIVE = "elective", "Elective"
        URGENT = "urgent", "Urgent"

    access = models.ForeignKey(VascularAccess, on_delete=models.CASCADE, related_name="procedures")
    procedure_type = models.CharField(max_length=32, choices=ProcedureType.choices)
    performed_on = models.DateField()
    operator = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="performed_procedures",
    )
    urgency = models.CharField(max_length=16, choices=Urgency.choices, default=Urgency.ELECTIVE)
    anesthesia = models.CharField(max_length=16, choices=Anesthesia.choices, blank=True)
    indication_complication = models.ForeignKey(
        "AccessComplication",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="treatment_procedures",
        help_text="Complication this procedure treats, if any.",
    )
    technical_success = models.BooleanField(
        null=True, blank=True, help_text="Immediate technical success; empty until assessed."
    )
    details = models.TextField(blank=True)

    class Meta:
        ordering = ["performed_on", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["access"],
                condition=models.Q(procedure_type="creation"),
                name="one_creation_procedure_per_access",
            ),
        ]

    def __str__(self):
        return f"{self.get_procedure_type_display()} on {self.access} ({self.performed_on})"

    @property
    def is_index_procedure(self):
        return self.procedure_type == ProcedureType.CREATION


class ComplicationType(models.TextChoices):
    NONMATURATION = "nonmaturation", "Nonmaturation"
    THROMBOSIS = "thrombosis", "Thrombosis"
    STENOSIS = "stenosis", "Stenosis"
    ACCESS_SITE_INFECTION = "access_site_infection", "Access site infection (fistula/graft)"
    CRBSI = "crbsi", "Catheter-related bloodstream infection"
    EXIT_SITE_INFECTION = "exit_site_infection", "Exit-site infection"
    TUNNEL_INFECTION = "tunnel_infection", "Tunnel infection"
    CATHETER_DYSFUNCTION = "catheter_dysfunction", "Catheter dysfunction"
    STEAL_SYNDROME = "steal_syndrome", "Steal syndrome / access-related ischemia"
    ANEURYSM = "aneurysm", "Aneurysm"
    PSEUDOANEURYSM = "pseudoaneurysm", "Pseudoaneurysm"
    BLEEDING = "bleeding", "Bleeding"
    HEMATOMA_SEROMA = "hematoma_seroma", "Hematoma / seroma"
    CENTRAL_VEIN_STENOSIS = "central_vein_stenosis", "Central vein stenosis"
    HIGH_OUTPUT_HEART_FAILURE = "high_output_heart_failure", "High-flow / high-output heart failure"
    NEUROPATHY = "neuropathy", "Access-related neuropathy"
    OTHER = "other", "Other"


class AccessComplication(TimeStampedModel):
    """Adverse event on an access; may be linked to the procedure treating it."""

    class Management(models.TextChoices):
        CONSERVATIVE = "conservative", "Conservative / observation"
        MEDICAL = "medical", "Medical therapy (antibiotics, anticoagulation…)"
        ENDOVASCULAR = "endovascular", "Endovascular intervention"
        SURGICAL = "surgical", "Surgical intervention"
        CATHETER_EXCHANGE_REMOVAL = "catheter_exchange_removal", "Catheter exchange or removal"
        ACCESS_ABANDONED = "access_abandoned", "Access abandoned"

    access = models.ForeignKey(
        VascularAccess, on_delete=models.CASCADE, related_name="complications"
    )
    complication_type = models.CharField(max_length=32, choices=ComplicationType.choices)
    onset_date = models.DateField()
    management = models.CharField(max_length=32, choices=Management.choices, blank=True)
    organism = models.CharField(
        max_length=255, blank=True, help_text="Culture result for infectious complications."
    )
    resolved = models.BooleanField(null=True, blank=True)
    resolution_date = models.DateField(null=True, blank=True)
    details = models.TextField(blank=True)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="recorded_complications",
    )

    class Meta:
        ordering = ["-onset_date"]

    def __str__(self):
        return f"{self.get_complication_type_display()} on {self.access} ({self.onset_date})"

    @property
    def is_early_thrombosis(self):
        """Thrombosis within 30 days of creation — reported separately."""
        return (
            self.complication_type == ComplicationType.THROMBOSIS
            and (self.onset_date - self.access.created_on)
            <= datetime.timedelta(days=EARLY_THROMBOSIS_WINDOW_DAYS)
        )
