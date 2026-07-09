import datetime

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from apps.core.models import TimeStampedModel, VoidableModel
from apps.patients.models import Patient

# Thrombosis within this many days of creation counts as "early thrombosis"
# in outcome reports (KDOQI-style early failure window). Fixed, not a
# RegistrySetting, so published rates stay comparable across years.
EARLY_THROMBOSIS_WINDOW_DAYS = 30

# A bridging catheter still in place past this dwell is a headline KPI
# (dashboard D6) and drives the removal alert escalation.
CATHETER_LONG_DWELL_DAYS = 90


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
    """Preoperative duplex ultrasound vascular mapping (one row per exam/side)."""

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
        indexes = [
            models.Index(fields=["patient", "-exam_date"], name="mapping_patient_date_idx"),
        ]

    def __str__(self):
        return f"Mapping {self.patient.registry_code} {self.get_side_display()} {self.exam_date}"


class AccessPlan(TimeStampedModel):
    """Access life-plan entry: the strategy decided before creation.

    The ordered chain of a patient's plans (including superseded ones)
    is the life-plan history; ``superseded_by`` links a revised plan to
    its replacement.
    """

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
    superseded_by = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="supersedes"
    )
    rationale = models.TextField(blank=True)

    class Meta:
        ordering = ["-plan_date"]
        indexes = [models.Index(fields=["status"], name="plan_status_idx")]

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


# Statuses that count as "active on the pathway" for worklists and the
# catheter-only-patient rule (an access that could still dialyze someone).
ACTIVE_ACCESS_STATUSES = (AccessStatus.MATURING, AccessStatus.READY, AccessStatus.IN_USE)


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


class VascularAccess(VoidableModel, TimeStampedModel):
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
        indexes = [
            models.Index(fields=["patient", "-created_on"], name="access_patient_date_idx"),
            models.Index(fields=["access_type"], name="access_type_idx"),
            # Hot worklist queries only ever want live accesses.
            models.Index(
                fields=["status"],
                name="access_active_status_idx",
                condition=models.Q(status__in=["maturing", "ready", "in_use"]),
            ),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(maturation_confirmed_on__isnull=True)
                | models.Q(maturation_confirmed_on__gte=models.F("created_on")),
                name="access_maturation_after_creation",
            ),
            models.CheckConstraint(
                condition=models.Q(first_cannulation_on__isnull=True)
                | models.Q(first_cannulation_on__gte=models.F("created_on")),
                name="access_cannulation_after_creation",
            ),
            models.CheckConstraint(
                condition=models.Q(abandoned_on__isnull=True)
                | models.Q(abandoned_on__gte=models.F("created_on")),
                name="access_abandonment_after_creation",
            ),
            models.CheckConstraint(
                condition=models.Q(removed_on__isnull=True)
                | models.Q(removed_on__gte=models.F("created_on")),
                name="access_removal_after_creation",
            ),
            # A coded end-of-use reason is meaningless without its date.
            models.CheckConstraint(
                condition=models.Q(abandonment_reason="") | models.Q(abandoned_on__isnull=False),
                name="access_abandon_reason_requires_date",
            ),
            models.CheckConstraint(
                condition=models.Q(removal_reason="") | models.Q(removed_on__isnull=False),
                name="access_removal_reason_requires_date",
            ),
        ]

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
        if self.is_catheter and self.status in (AccessStatus.MATURING, AccessStatus.READY):
            errors["status"] = "A catheter is usable immediately: it is never maturing/ready."
        if errors:
            raise ValidationError(errors)

    # ----- classification helpers -------------------------------------

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
    def is_active(self):
        """Access still on the pathway (maturing, ready or in use)."""
        return self.status in ACTIVE_ACCESS_STATUSES and not self.is_voided

    # ----- computed intervals (never stored) ---------------------------

    @property
    def days_to_maturation(self):
        if self.maturation_confirmed_on is None:
            return None
        return (self.maturation_confirmed_on - self.created_on).days

    @property
    def days_to_first_cannulation(self):
        if self.first_cannulation_on is None:
            return None
        return (self.first_cannulation_on - self.created_on).days

    @property
    def days_to_abandonment(self):
        """Functional lifespan; the secondary-patency interval when abandoned."""
        if self.abandoned_on is None:
            return None
        return (self.abandoned_on - self.created_on).days

    @property
    def catheter_days(self):
        """Dwell days for catheter episodes: insertion → removal (or today).

        This is the "catheter clock" shown on the timeline and the
        denominator unit for CRBSI-per-1000-catheter-days analytics.
        """
        if not self.is_catheter:
            return None
        end = self.removed_on or datetime.date.today()
        return (end - self.created_on).days

    @property
    def catheter_over_90_days(self):
        """Long-dwell flag (dashboard D6 / removal-alert escalation)."""
        days = self.catheter_days
        return days is not None and days > CATHETER_LONG_DWELL_DAYS

    @property
    def end_of_use_date(self):
        """Date the access permanently stopped being usable, if it has."""
        return self.abandoned_on or self.removed_on


class TipPosition(models.TextChoices):
    RIGHT_ATRIUM = "right_atrium", "Right atrium"
    CAVOATRIAL_JUNCTION = "cavoatrial_junction", "Cavoatrial junction"
    SVC = "svc", "Superior vena cava"
    OTHER = "other", "Other"
    NOT_RECORDED = "not_recorded", "Not recorded"


class InsertionTechnique(models.TextChoices):
    US_AND_FLUORO = "us_and_fluoro", "Ultrasound + fluoroscopy"
    US_ONLY = "us_only", "Ultrasound only"
    LANDMARK = "landmark", "Landmark technique"


class ReasonForCatheter(models.TextChoices):
    URGENT_START = "urgent_start", "Urgent dialysis start"
    BRIDGE_AVF_MATURING = "bridge_avf_maturing", "Bridge while AVF/AVG matures"
    OPTIONS_EXHAUSTED = "options_exhausted", "Permanent access options exhausted"
    PATIENT_REFUSAL_OF_AVF = "patient_refusal_of_avf", "Patient refusal of AVF/AVG"
    OTHER = "other", "Other"


class CatheterDetail(TimeStampedModel):
    """Catheter-specific attributes, 1:1 with catheter-type accesses.

    Vertical partition: keeps ~10 catheter-only columns off the fistula
    rows and makes the W5 "reason for catheter" a coded field from day 1.
    """

    access = models.OneToOneField(
        VascularAccess, on_delete=models.CASCADE, related_name="catheter_detail"
    )
    device = models.ForeignKey(
        "Device", null=True, blank=True, on_delete=models.PROTECT, related_name="catheter_details"
    )
    lumen_count = models.PositiveSmallIntegerField(null=True, blank=True)
    catheter_length_cm = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True)
    tip_position = models.CharField(max_length=24, choices=TipPosition.choices, blank=True)
    insertion_technique = models.CharField(
        max_length=24, choices=InsertionTechnique.choices, blank=True
    )
    reason_for_catheter = models.CharField(max_length=32, choices=ReasonForCatheter.choices)
    exit_site_note = models.CharField(max_length=255, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(lumen_count__isnull=True)
                | models.Q(lumen_count__gte=1, lumen_count__lte=3),
                name="catheter_lumen_count_1_to_3",
            ),
        ]

    def __str__(self):
        return f"Catheter detail for {self.access}"

    def clean(self):
        if self.access_id and not self.access.is_catheter:
            raise ValidationError(
                {"access": "Catheter details can only be attached to catheter-type accesses."}
            )


class MaturationAssessmentType(models.TextChoices):
    POSTOP_CHECK = "postop_check", "Post-operative check (~2 weeks)"
    CLINICAL = "clinical", "Clinical assessment"
    DUPLEX = "duplex", "Duplex ultrasound"
    PRE_CANNULATION = "pre_cannulation", "Pre-cannulation check"


class MaturationVerdict(models.TextChoices):
    ON_TRACK = "on_track", "Maturing as expected"
    MATURE = "mature", "Mature — ready for cannulation"
    DELAYED = "delayed", "Delayed — intervention to consider"
    FAILED = "failed", "Failed maturation"


class MaturationAssessment(VoidableModel, TimeStampedModel):
    """Structured AVF/AVG follow-up (2-week check, 4–6-week assessment…).

    A ``mature`` verdict is the trigger for setting
    ``VascularAccess.maturation_confirmed_on`` (workflow responsibility,
    not an automatic write).
    """

    access = models.ForeignKey(
        VascularAccess, on_delete=models.CASCADE, related_name="maturation_assessments"
    )
    assessment_date = models.DateField()
    assessment_type = models.CharField(max_length=24, choices=MaturationAssessmentType.choices)
    thrill_present = models.BooleanField(null=True, blank=True)
    bruit_present = models.BooleanField(null=True, blank=True)
    outflow_vein_diameter_mm = models.DecimalField(
        max_digits=4, decimal_places=1, null=True, blank=True
    )
    flow_volume_ml_min = models.PositiveIntegerField(null=True, blank=True)
    vein_depth_mm = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True)
    verdict = models.CharField(max_length=16, choices=MaturationVerdict.choices)
    assessed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="maturation_assessments",
    )
    comments = models.TextField(blank=True)

    class Meta:
        ordering = ["assessment_date", "id"]
        indexes = [
            models.Index(fields=["access", "assessment_date"], name="maturation_access_date_idx"),
        ]

    def __str__(self):
        return f"{self.get_assessment_type_display()} on {self.access} ({self.assessment_date})"

    def clean(self):
        if self.access_id and self.assessment_date and self.assessment_date < self.access.created_on:
            raise ValidationError(
                {"assessment_date": "Assessment cannot precede access creation."}
            )


class DeviceType(models.TextChoices):
    GRAFT = "graft", "Prosthetic graft"
    TUNNELED_CATHETER = "tunneled_catheter", "Tunneled cuffed catheter"
    TEMPORARY_CATHETER = "temporary_catheter", "Temporary catheter"
    STENT = "stent", "Stent"
    STENT_GRAFT = "stent_graft", "Stent graft"
    BALLOON = "balloon", "Angioplasty balloon"
    HERO_COMPONENT = "hero_component", "HeRO component"
    OTHER = "other", "Other"


class Device(TimeStampedModel):
    """Catalog of implantable devices/materials; one row per product+size."""

    device_type = models.CharField(max_length=24, choices=DeviceType.choices)
    manufacturer = models.CharField(max_length=100)
    model_name = models.CharField(max_length=100)
    size_spec = models.CharField(
        max_length=50, blank=True, help_text='e.g. "6 mm × 40 cm", "23 cm, 14.5 F"'
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["manufacturer", "model_name", "size_spec"]
        constraints = [
            models.UniqueConstraint(
                fields=["device_type", "manufacturer", "model_name", "size_spec"],
                name="unique_device_catalog_entry",
            ),
        ]

    def __str__(self):
        size = f" {self.size_spec}" if self.size_spec else ""
        return f"{self.manufacturer} {self.model_name}{size}"


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


class AccessProcedure(VoidableModel, TimeStampedModel):
    """Every operation on an access: the index creation and all revisions.

    The index creation carries ``procedure_type=CREATION``; any later
    (non-voided) row on the same access ends its primary patency interval.
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
    devices = models.ManyToManyField(
        Device,
        through="ProcedureDevice",
        related_name="procedures",
        blank=True,
        help_text="Implanted/used devices with lot traceability.",
    )
    details = models.TextField(blank=True)

    class Meta:
        ordering = ["performed_on", "id"]
        indexes = [
            models.Index(fields=["access", "performed_on"], name="procedure_access_date_idx"),
            models.Index(fields=["procedure_type"], name="procedure_type_idx"),
        ]
        constraints = [
            # Voided rows drop out of the uniqueness rule so a mis-entered
            # creation can be voided and re-entered.
            models.UniqueConstraint(
                fields=["access"],
                condition=models.Q(procedure_type="creation", is_voided=False),
                name="one_creation_procedure_per_access",
            ),
        ]

    def __str__(self):
        return f"{self.get_procedure_type_display()} on {self.access} ({self.performed_on})"

    @property
    def is_index_procedure(self):
        return self.procedure_type == ProcedureType.CREATION


class ProcedureDevice(TimeStampedModel):
    """Devices used in a procedure, with lot/serial for recall traceability."""

    procedure = models.ForeignKey(
        AccessProcedure, on_delete=models.CASCADE, related_name="device_uses"
    )
    device = models.ForeignKey(Device, on_delete=models.PROTECT, related_name="uses")
    lot_number = models.CharField(max_length=64, blank=True)
    serial_number = models.CharField(max_length=64, blank=True)
    quantity = models.PositiveSmallIntegerField(default=1)

    class Meta:
        ordering = ["id"]
        constraints = [
            models.CheckConstraint(condition=models.Q(quantity__gte=1), name="device_quantity_positive"),
        ]

    def __str__(self):
        return f"{self.device} × {self.quantity} in {self.procedure}"


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


# Complication types eligible for the 1:1 detail extensions.
INFECTION_COMPLICATION_TYPES = {
    ComplicationType.ACCESS_SITE_INFECTION,
    ComplicationType.CRBSI,
    ComplicationType.EXIT_SITE_INFECTION,
    ComplicationType.TUNNEL_INFECTION,
}
THROMBOSIS_DYSFUNCTION_TYPES = {
    ComplicationType.THROMBOSIS,
    ComplicationType.STENOSIS,
    ComplicationType.CATHETER_DYSFUNCTION,
}


class AccessComplication(VoidableModel, TimeStampedModel):
    """Adverse event on an access; may be linked to the procedure treating it."""

    class TriageStatus(models.TextChoices):
        # Nurse-reported events start pending; a physician must code them.
        PENDING = "pending", "Pending physician triage"
        TRIAGED = "triaged", "Triaged"

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
    triage_status = models.CharField(
        max_length=16, choices=TriageStatus.choices, default=TriageStatus.TRIAGED
    )
    management = models.CharField(max_length=32, choices=Management.choices, blank=True)
    resolved = models.BooleanField(null=True, blank=True)
    resolution_date = models.DateField(null=True, blank=True)
    details = models.TextField(blank=True)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="recorded_complications",
    )

    class Meta:
        ordering = ["-onset_date"]
        indexes = [
            models.Index(fields=["access", "onset_date"], name="complication_access_date_idx"),
            models.Index(fields=["complication_type"], name="complication_type_idx"),
            # Alert A2 scans only untriaged reports.
            models.Index(
                fields=["triage_status"],
                name="complication_pending_idx",
                condition=models.Q(triage_status="pending"),
            ),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(resolution_date__isnull=True)
                | models.Q(resolution_date__gte=models.F("onset_date")),
                name="complication_resolution_after_onset",
            ),
        ]

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


class InfectionOutcome(models.TextChoices):
    RESOLVED = "resolved", "Resolved"
    RECURRENT = "recurrent", "Recurrent"
    METASTATIC_INFECTION = "metastatic_infection", "Metastatic infection"
    DEATH_RELATED = "death_related", "Contributed to death"
    UNKNOWN = "unknown", "Unknown"


class InfectionDetail(TimeStampedModel):
    """Infection specifics, 1:1 with infection-type complications."""

    complication = models.OneToOneField(
        AccessComplication, on_delete=models.CASCADE, related_name="infection_detail"
    )
    blood_cultures_taken = models.BooleanField(null=True, blank=True)
    organism = models.CharField(
        max_length=255, blank=True, help_text="Culture result (free text; coded list later)."
    )
    antibiotic_therapy = models.CharField(max_length=255, blank=True)
    hospitalization_required = models.BooleanField(null=True, blank=True)
    access_removed_or_exchanged = models.BooleanField(
        null=True, blank=True,
        help_text="Catheter pulled / graft excised because of this infection.",
    )
    outcome = models.CharField(max_length=24, choices=InfectionOutcome.choices, blank=True)

    class Meta:
        verbose_name = "infection detail"

    def __str__(self):
        return f"Infection detail for {self.complication}"

    def clean(self):
        if (
            self.complication_id
            and self.complication.complication_type not in INFECTION_COMPLICATION_TYPES
        ):
            raise ValidationError(
                {"complication": "Infection details require an infection-type complication."}
            )


class SuspectedCause(models.TextChoices):
    JUXTA_ANASTOMOTIC_STENOSIS = "juxta_anastomotic_stenosis", "Juxta-anastomotic stenosis"
    OUTFLOW_STENOSIS = "outflow_stenosis", "Outflow stenosis"
    CENTRAL_STENOSIS = "central_stenosis", "Central vein stenosis"
    INTRA_ACCESS_STENOSIS = "intra_access_stenosis", "Intra-access stenosis"
    HYPOTENSION = "hypotension", "Hypotension"
    HYPERCOAGULABILITY = "hypercoagulability", "Hypercoagulability"
    EXTERNAL_COMPRESSION = "external_compression", "External compression"
    FIBRIN_SHEATH = "fibrin_sheath", "Fibrin sheath (catheter)"
    MALPOSITION = "malposition", "Malposition (catheter)"
    UNKNOWN = "unknown", "Unknown"


class ThrombosisDysfunctionDetail(TimeStampedModel):
    """Cause/location specifics, 1:1 with thrombosis/stenosis/dysfunction."""

    complication = models.OneToOneField(
        AccessComplication, on_delete=models.CASCADE, related_name="thrombosis_detail"
    )
    suspected_cause = models.CharField(max_length=32, choices=SuspectedCause.choices, blank=True)
    stenosis_location = models.CharField(max_length=100, blank=True)
    thrombolytic_lock_used = models.BooleanField(null=True, blank=True)
    flow_restored = models.BooleanField(null=True, blank=True)

    class Meta:
        verbose_name = "thrombosis/dysfunction detail"

    def __str__(self):
        return f"Thrombosis/dysfunction detail for {self.complication}"

    def clean(self):
        if (
            self.complication_id
            and self.complication.complication_type not in THROMBOSIS_DYSFUNCTION_TYPES
        ):
            raise ValidationError(
                {
                    "complication": (
                        "This detail record requires a thrombosis, stenosis or "
                        "catheter-dysfunction complication."
                    )
                }
            )
