from django.contrib.auth.models import AbstractUser
from django.db import models


class Role(models.TextChoices):
    """Clinical roles that drive role-based access control.

    - Vascular surgeon: full access to all registry data.
    - Nephrologist: views/comments on own patients, confirms dialysis use.
    - Dialysis nurse: adds dialysis functionality logs.
    - Registry coordinator: data entry and follow-up tasks.
    - Researcher: dashboards and anonymized export only.
    """

    VASCULAR_SURGEON = "vascular_surgeon", "Vascular surgeon"
    NEPHROLOGIST = "nephrologist", "Nephrologist"
    DIALYSIS_NURSE = "dialysis_nurse", "Dialysis nurse"
    REGISTRY_COORDINATOR = "registry_coordinator", "Registry coordinator"
    RESEARCHER = "researcher", "Admin / research user"


class User(AbstractUser):
    role = models.CharField(max_length=32, choices=Role.choices)
    phone = models.CharField(max_length=32, blank=True)
    institution = models.CharField(
        max_length=255,
        blank=True,
        help_text="Hospital, clinic or dialysis center the user works at.",
    )
    # Required in practice for dialysis nurses (app-enforced): scopes the
    # nurse portal to their center's patients.
    dialysis_center = models.ForeignKey(
        "patients.DialysisCenter",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="staff",
    )

    class Meta:
        ordering = ["last_name", "first_name", "username"]

    def __str__(self):
        label = self.get_full_name() or self.username
        return f"{label} ({self.get_role_display()})" if self.role else label

    @property
    def is_vascular_surgeon(self):
        return self.role == Role.VASCULAR_SURGEON

    @property
    def is_nephrologist(self):
        return self.role == Role.NEPHROLOGIST

    @property
    def is_dialysis_nurse(self):
        return self.role == Role.DIALYSIS_NURSE

    @property
    def is_registry_coordinator(self):
        return self.role == Role.REGISTRY_COORDINATOR

    @property
    def is_researcher(self):
        return self.role == Role.RESEARCHER
