# Dialysis Vascular Access Registry

A patient-centered registry for a vascular surgery and nephrology service in
Georgia, following the complete dialysis access pathway:

> CKD 4–5 / predialysis referral → access planning → vascular mapping →
> AVF/AVG/catheter creation → maturation → first cannulation → dialysis
> functionality → complications → revisions/interventions → catheter removal →
> access abandonment → death / transplant / transfer.

**Stack:** Django 5.2 (LTS) · PostgreSQL 16 · Python 3.11+

## Data model

The schema is patient-centered: every clinical table hangs off `Patient`, and
personal identifiers exist *only* on `Patient` (each patient carries a stable
pseudonymous `registry_code`, e.g. `DA-000042`, for future anonymized exports).

| App | Models | Purpose |
| --- | --- | --- |
| `core` | `RegistrySetting` (+ abstract `TimeStampedModel`, `VoidableModel`) | Superuser-editable clinical thresholds; shared timestamp and void-instead-of-delete mixins. |
| `accounts` | `User` | Custom user with clinical `role` (vascular surgeon, nephrologist, dialysis nurse, registry coordinator, researcher); nurses carry a dialysis-center scope. |
| `patients` | `DialysisCenter`, `Patient`, `PatientStatusEvent`, `ClinicalNote` | Collaborating centers; demographics, CKD stage and renal history, comorbidities; append-only pathway status history (predialysis → HD → transplant/transfer/death/LTFU) with a denormalized `current_status`; free-text clinical commentary. |
| `vascular_access` | `VesselMapping`, `AccessPlan`, `VascularAccess`, `CatheterDetail`, `MaturationAssessment`, `AccessProcedure`, `Device`, `ProcedureDevice`, `AccessComplication`, `InfectionDetail`, `ThrombosisDysfunctionDetail` | Preoperative duplex mapping; access life-plan; one row per access (all nine access types) with pathway milestone dates; catheter-specific detail; structured maturation follow-up; every operation (index creation + all revisions) with device traceability; every adverse event with infection/thrombosis detail extensions. |
| `dialysis` | `DialysisSessionLog` | Nurse-entered per-session functionality records (cannulation success, Qb, pressures, problems), scoped to a dialysis center. |
| `followup` | `FollowUpTask` | Worklist engine: system- and manually-created tasks with due dates, deferral rules and dedupe keys. |
| `alerts` | `Alert` | Persisted instances of spec alert rules A1–A15 with severity, snooze and note-required resolution. |
| `research` | `ExportLog` | Trail of every anonymized export (who, what, when, filters). |
| `audit` | `AuditLog` | Append-only, actor- and IP-attributed create/update/delete trail with per-field diffs, written automatically for all clinical models. |

### Access types

Radiocephalic AVF · Brachiocephalic AVF · Brachiobasilic AVF · Transposed
basilic AVF · Prosthetic AVG · Tunneled cuffed dialysis catheter · Temporary
dialysis catheter · HeRO graft · Complex access.

### Outcome definitions anchored in the schema

| Outcome | Source |
| --- | --- |
| Technical success | `AccessProcedure.technical_success` on the index (creation) procedure |
| Time to maturation | `VascularAccess.created_on` → `maturation_confirmed_on` |
| First (successful) cannulation | `first_cannulation_on` / `first_successful_cannulation_on` |
| Dialysis functionality | `DialysisSessionLog` rows + nephrologist confirmation (`dialysis_use_confirmed_by/_on`) |
| Primary patency | creation → first post-creation `AccessProcedure` or thrombosis |
| Assisted primary patency | creation → first thrombosis (`AccessComplication`) |
| Secondary patency | creation → `abandoned_on` |
| Nonmaturation | `AccessComplication` type or `FAILED_MATURATION` status |
| Early thrombosis | thrombosis within 30 days of creation (`is_early_thrombosis`) |
| Infections | access-site infection, CRBSI, exit-site, tunnel infection complication types |
| Catheter dysfunction / removal | complication type + `removed_on` / `removal_reason` |
| Reintervention | any non-creation `AccessProcedure` |
| Access abandonment | `abandoned_on` + coded `abandonment_reason` |
| Death / transplant / transfer | `PatientStatusEvent` history |

## Getting started

```bash
# 1. Python environment
python3 -m venv .venv
.venv/bin/pip install -r requirements/dev.txt

# 2. Configuration
cp .env.example .env        # then edit SECRET_KEY etc.

# 3. Database (PostgreSQL 16 via Docker)
docker compose up -d db

# 4. Migrate, create the first user, run
.venv/bin/python manage.py migrate
.venv/bin/python manage.py createsuperuser
.venv/bin/python manage.py runserver
```

Data entry currently happens through the Django admin at `/admin/`
(header: “Dialysis Vascular Access Registry”). All clinical writes are
recorded in the audit log automatically, attributed to the logged-in user.

```bash
# Run the test suite (any DATABASE_URL works; sqlite is fine for tests)
DATABASE_URL=sqlite:///test.sqlite3 .venv/bin/python manage.py test
```

Settings live in `config/settings/` (`base.py`, `development.py`,
`production.py`) and read configuration from the environment
(`DJANGO_SETTINGS_MODULE`, `SECRET_KEY`, `DATABASE_URL`, `ALLOWED_HOSTS`).

## Roles (enforcement roadmap)

| Role | Intended access |
| --- | --- |
| Vascular surgeon | Full access |
| Nephrologist | View/comment on own patients, confirm dialysis use |
| Dialysis nurse | Add dialysis functionality logs |
| Registry coordinator | Data entry and follow-up tasks |
| Admin / research user | Dashboards and anonymized export |

Roles are modeled on `accounts.User.role`; per-role permission enforcement,
role-scoped views, coordinator follow-up tasks, dashboards and the anonymized
research export are the next build stages.
