# Product Specification — Dialysis Vascular Access Registry

| | |
|---|---|
| **Status** | Approved working spec for development |
| **Version** | 1.0 (2026-07-09) |
| **Service** | Vascular surgery + nephrology dialysis access service, Georgia |
| **Stack** | Django 5.2 · PostgreSQL 16 · server-rendered UI (Django templates), progressive enhancement only where needed |
| **Relation to code** | Model, field and status names in this spec match the implemented schema (`apps/patients`, `apps/vascular_access`, `apps/dialysis`, `apps/audit`, `apps/accounts`). New models required by this spec are marked **(new)**. |

---

## 1. Product vision

**One sentence:** a single source of truth for every dialysis access patient in the service — from predialysis referral to access abandonment — that runs the daily clinical workflow and produces research-grade outcome data as a by-product.

**The problem it solves.** Access history today is scattered across operative logs, dialysis center paper records and memory. Nobody can reliably answer "which of my fistulas from last year are still working?", "which patients are catheter-dependent and why?", or "is this patient's maturation overdue?". Follow-up is driven by whoever remembers.

**What the product is:**

1. **A patient-centered longitudinal record.** The unit of the registry is the patient, not the operation. Every mapping, plan, operation, complication, dialysis session and status change hangs off one patient timeline.
2. **A workflow engine.** Worklists and alerts drive follow-up: overdue maturation checks, catheters that should have come out, complications awaiting treatment. The registry tells the team what to do next, not just what happened.
3. **A research instrument.** Because outcomes (patency, maturation, infection) are anchored to structured dates and coded events, KDOQI-style endpoints are computed, never transcribed. Anonymized export by `registry_code` is built in.

**Non-goals (v1):** not an EHR (no labs, prescriptions, imaging PACS), not a dialysis machine integration, not a billing system, not patient-facing.

**Success criteria (12 months after launch):**
- 100 % of the service's access operations captured within 48 h of the procedure.
- Every in-use access has a dialysis functionality log at least monthly.
- Zero tunneled catheters "forgotten" > 30 days after the AVF is confirmed working.
- Patency and infection reports for any period generated in < 1 minute, no chart review.

---

## 2. Main users and their permissions

### 2.1 Roles

| Role (`accounts.Role`) | Who | One-line mandate |
|---|---|---|
| `vascular_surgeon` | Operating surgeons of the service | Full clinical read/write on all patients |
| `nephrologist` | Referring / treating nephrologists | Follow **own** patients, comment, confirm dialysis use |
| `dialysis_nurse` | Nurses at collaborating dialysis centers | Report per-session access functionality and problems |
| `registry_coordinator` | Service administrator / study nurse | Data entry, scheduling, follow-up task management, data quality |
| `researcher` | Admin/research user | Aggregate dashboards + anonymized export, **no identifiable data** |
| *(superuser)* | System administrator | User accounts, reference data, technical settings. Not a clinical role. |

### 2.2 Permission matrix

C = create, R = read, U = update, D = delete (soft/void, always audited). "own" = row-level restriction, see 2.3.

| Data | Surgeon | Nephrologist | Dialysis nurse | Coordinator | Researcher |
|---|---|---|---|---|---|
| Patient demographics & identity | CRUD | R (own) | R (minimal: name, registry code, access in use) | CRU | — (pseudonymous only) |
| Referral / CKD data | CRUD | RU (own) | — | CRU | aggregate |
| Status events (death/transplant/transfer) | CRUD | CR (own) | — | CRU | aggregate |
| Vessel mapping | CRUD | R (own) | — | CR (transcription) | aggregate |
| Access plan | CRUD | R (own) + comment | — | R | aggregate |
| Vascular access record | CRUD | R (own) | R (cannulation-relevant fields) | RU (milestone dates) | aggregate |
| Procedures (creation, revisions) | CRUD | R (own) | — | R | aggregate |
| Complications | CRUD | CR (own) | C (report) R (own reports) | CRU | aggregate |
| Dialysis session logs | R | R (own) | CRU (own entries, same-day edit) | R | aggregate |
| Dialysis-use confirmation | R | **CU (own)** — their signature action | — | — | aggregate |
| Clinical notes | CRUD (own notes) | CR (own patients) | — | CR | — |
| Follow-up tasks **(new)** | CRUD | R (own) | — | CRUD | — |
| Alerts | R + resolve | R (own) | R (their center) | R + resolve | — |
| Dashboards | all | own-patient subset | their center subset | operational + data quality | all (aggregate) |
| Anonymized export | R | — | — | — | **CR** |
| Audit log | R | — | — | R | — |
| User management | — | — | — | — | — (superuser only) |

Hard rules:
- Nobody deletes clinical rows physically; "delete" = voiding with reason, `AuditLog` keeps the trail (already enforced by signals).
- Researcher role never sees `national_id`, names, phone, address, exact dates of birth (year only in export).
- Every write is attributed via `AuditActorMiddleware` (implemented).

### 2.3 Row-level rules

- **Nephrologist "own patients":** `patient.responsible_nephrologist == user`, plus patients they are explicitly shared on (share table, advanced version).
- **Dialysis nurse "their center":** nurse account carries `institution`; sees only patients whose `patient.dialysis_center` matches, and only the access currently in use (type, side, site, cannulation notes, warnings) — not full history or comorbidities.
- **Coordinator** sees everything but cannot alter physician judgment fields (e.g. `technical_success`, complication type after physician entry) — those edits require surgeon role.

---

## 3. Main modules

| # | Module | Django app | Contents | Status |
|---|---|---|---|---|
| M1 | Patient registry | `patients` | Demographics, referral/CKD, comorbidities, status event history, clinical notes | Schema done |
| M2 | Planning & mapping | `vascular_access` | `VesselMapping`, `AccessPlan` | Schema done |
| M3 | Access lifecycle | `vascular_access` | `VascularAccess` with milestone dates and status machine | Schema done |
| M4 | Procedures | `vascular_access` | `AccessProcedure`: index creation + every reintervention | Schema done |
| M5 | Complications | `vascular_access` | `AccessComplication` incl. infections, thrombosis, dysfunction | Schema done |
| M6 | Dialysis functionality | `dialysis` | `DialysisSessionLog` + nephrologist use-confirmation | Schema done |
| M7 | Follow-up & tasks | `followup` **(new)** | `FollowUpTask` (type, patient/access, due date, assignee role, status), worklists | To build |
| M8 | Alerts | `alerts` **(new)** | Rule-evaluated `Alert` rows (see §10), in-app first, email later | To build |
| M9 | Dashboards & analytics | `analytics` **(new)** | Read-only aggregate queries, KM patency engine (advanced) | To build |
| M10 | Research export | `research` **(new)** | Anonymized CSV bundles, export log (who exported what, when) | To build |
| M11 | Audit & security | `audit`, `accounts` | Audit trail, roles, row-level permissions | Trail done; permissions to build |
| M12 | Administration | Django admin | Users, reference thresholds (e.g. maturation deadline days), data corrections | Admin done |

---

## 4. Patient journey (predialysis referral → access abandonment)

Each stage shows: what happens, what is recorded, who records it, and the resulting system state (`patient.current_status` / `access.status`).

| Stage | Clinical event | Recorded as | By | System state after |
|---|---|---|---|---|
| 0. Referral | Nephrologist refers CKD 4–5 patient for access | `Patient` created: referral_date, ckd_stage_at_referral, primary_renal_disease, comorbidities; initial `PatientStatusEvent` | Coordinator (or surgeon) | patient: `predialysis` (or `on_hemodialysis` if urgent-start) |
| 1. Planning | Surgeon reviews patient, decides strategy | `AccessPlan`: planned type + side, rationale | Surgeon | plan: `planned` |
| 2. Mapping | Duplex vein/artery mapping | `VesselMapping`: diameters, calcification, central vein concern; plan may be revised | Surgeon / coordinator transcribes | — |
| 3. Creation | AVF/AVG creation or catheter insertion | `VascularAccess` + index `AccessProcedure` (type `creation`, technical_success) | Surgeon (op data), coordinator (admin fields) | access: `maturing` (fistula/graft) or `in_use` (catheter); plan: `performed` |
| 4. Maturation | Postop checks at 2 w, 4–6 w; duplex if doubt | `maturation_confirmed_on` set, or nonmaturation pathway (complication + intervention or `failed_maturation`) | Surgeon; tasks by coordinator | access: `ready`, or `failed_maturation` |
| 5. First cannulation | Dialysis center starts using the access | `first_cannulation_on`, `first_successful_cannulation_on`; session logs begin | Nurse logs sessions; coordinator/surgeon set dates | access: `in_use` |
| 6. Confirmed function | Nephrologist certifies the access supports adequate dialysis | `dialysis_use_confirmed_by/_on` | Nephrologist | — |
| 7. Catheter exit | Bridging TDC removed after AVF proven | `catheter_removal` procedure + `removed_on`, reason `no_longer_needed` on the TDC access | Surgeon; task-driven | TDC access: `removed` |
| 8. Surveillance | Ongoing session logs; problems detected early | `DialysisSessionLog` rows; alerts on patterns | Nurse | — |
| 9. Complications & reinterventions | Stenosis, thrombosis, infection … treated | `AccessComplication` + linked `AccessProcedure` | Any clinical role reports; surgeon codes treatment | access stays `in_use` or → `abandoned` |
| 10. End of access | Access permanently unusable or unnecessary | `abandoned_on` + coded reason; next access loops to stage 1 | Surgeon | access: `abandoned` |
| 11. End of follow-up | Death / transplant / transfer / lost | `PatientStatusEvent` | Coordinator / nephrologist | patient: `deceased` / `transplanted` / `transferred_out` / `lost_to_follow_up` |

State machines (enforced in forms, not just convention):

- **Patient:** `predialysis → on_hemodialysis → (transplanted | transferred_out | deceased | lost_to_follow_up)`, with returns to `on_hemodialysis` allowed (failed transplant, returning transfer).
- **Fistula/graft access:** `maturing → ready → in_use → abandoned`, with shortcuts `maturing → failed_maturation`, `maturing → in_use` (cannulated without formal maturity note — allowed, flagged), any → `abandoned`.
- **Catheter access:** `in_use → removed`. A catheter is never `maturing`.

---

## 5. Core workflows

Format per workflow: **Actor · Trigger → Steps → Data → System actions**. All forms are single-page, save-and-return-to-patient-timeline.

### W1. New patient registration
**Actor:** Coordinator (surgeon can). **Trigger:** referral letter / phone from nephrology.
1. Search by national ID and name to prevent duplicates (hard warn on match).
2. Fill Patient form: identity, contacts, region, dialysis center (if HD), referral block (date, CKD stage, renal disease, responsible nephrologist + surgeon), comorbidity checklist.
3. Save → registry code auto-assigned (`DA-000123`); initial status event created (`predialysis` or `on_hemodialysis` + dialysis_start_date).
**System:** creates follow-up task "Plan access" due +14 days assigned to surgeon; patient appears on "New referrals" worklist.

### W2. Access planning
**Actor:** Surgeon. **Trigger:** "Plan access" task or clinic visit.
1. Open patient timeline → "New plan".
2. Record planned access type + side, rationale, link the mapping used (if done).
3. If mapping missing → one-click creates "Vascular mapping needed" task instead of blocking.
**Data:** `AccessPlan` (status `planned`).
**System:** closes planning task; creates "Schedule creation procedure" task for coordinator. Plan visible (read + comment) to the responsible nephrologist.

### W3. Vascular mapping
**Actor:** Surgeon performs; coordinator may transcribe a paper report. **Trigger:** planning requirement.
1. New `VesselMapping` from patient timeline: exam date, side, cephalic/basilic vein and radial/brachial artery diameters (mm), calcification, central-vein concern, findings text.
2. If a plan exists, prompt "update plan based on mapping?" → opens plan edit.
**System:** flags mapping values below configurable thresholds (e.g. cephalic vein < 2.0 mm) as a visual warning on the planning screen — advisory only, never blocking.

### W4. AVF/AVG creation
**Actor:** Surgeon (clinical), coordinator (logistics). **Trigger:** operation performed.
1. From the plan (or directly): "Record new access". Form pre-fills type/side from plan.
2. Access block: type, laterality, site, graft material (AVG/HeRO).
3. Index procedure block (saved as `AccessProcedure` type `creation`): date, operator, urgency, anesthesia, technical success, operative details.
**System:** access status `maturing`; plan → `performed`; auto-creates tasks: "2-week wound/thrill check" (due +14 d) and "Maturation assessment" (due +42 d, configurable). If technical_success = No → task "Early review" due +7 d and alert to surgeon.

### W5. Tunneled dialysis catheter insertion
**Actor:** Surgeon. **Trigger:** urgent-start HD or bridge while AVF matures.
1. "Record new access", type `tunneled_cuffed_catheter` (or `temporary_catheter`), site (IJ/subclavian/femoral) + side, insertion procedure row (technical success, details).
2. Form requires "reason catheter, not fistula" (dropdown: urgent start, AVF maturing, all options exhausted, patient refusal of AVF, other) — stored in `notes` in MVP, coded field in advanced.
**System:** status `in_use` immediately; starts the **catheter clock** (dwell counter shown on patient timeline). Temporary catheter → alert at day 14 ("convert to TDC or remove"). TDC with no permanent-access plan → task "Plan permanent access" due +14 d. Catheter-days counters feed the CRBSI dashboard.

### W6. Follow-up after AVF creation
**Actor:** Coordinator drives worklist; surgeon does the assessment. **Trigger:** auto-created tasks from W4.
1. **2-week check:** wound, thrill/bruit present? Recorded as a clinical note from a mini-form (structured yes/no + comment). Absent thrill → surgeon alert, "Duplex now" task.
2. **4–6-week maturation assessment:** clinical ± duplex. Outcomes:
   - Mature → set `maturation_confirmed_on` → status `ready` → system notifies nephrologist + creates "Inform dialysis center — ready for first cannulation" task.
   - Not yet mature → record `nonmaturation` complication (management pending), task "Fistulogram / intervention decision" due +14 d.
3. **8–12-week decision:** still not usable after salvage → status `failed_maturation`, abandonment fields set (reason `nonmaturation`) → planning workflow restarts (W2).
**System:** overdue maturation tasks escalate to the alert list at +7 days.

### W7. Dialysis center functionality reporting
**Actor:** Dialysis nurse. **Trigger:** each session (minimum: first sessions, monthly, and any problem session).
1. Nurse opens their center's patient list → patient → "Log session" (mobile-friendly single form).
2. Fields: date, cannulation successful (fistula/graft), Qb achieved, arterial/venous pressures, problem code, session completed, note.
3. First-ever log on an access asks: "Was this the first cannulation?" → sets `first_cannulation_on`; first log with successful + completed session sets `first_successful_cannulation_on`; access status → `in_use`.
**System:** problem patterns raise alerts (§10: two failed cannulations, low Qb ×2, suspected infection → same-day surgeon alert). Nephrologist sees a "confirm dialysis use" button once ≥ N successful sessions (default 6) — one click sets `dialysis_use_confirmed_by/_on`.

### W8. Complication reporting
**Actor:** anyone clinical (nurse reports suspicion; surgeon/nephrologist code it). **Trigger:** clinical event.
1. From access page: "Report complication" → type (coded list incl. thrombosis, stenosis, CRBSI, exit-site, tunnel infection, catheter dysfunction, steal, aneurysm/pseudoaneurysm, bleeding), onset date, details, organism if cultured.
2. Management field starts `pending` for nurse-reported events; surgeon completes coding (conservative / medical / endovascular / surgical / exchange-removal / abandoned).
**System:** every new complication alerts the responsible surgeon (infections marked urgent); creates "Treat/triage complication" task; if management = `access_abandoned` → guided abandonment (dates + reason + "plan next access?" prompt). Thrombosis auto-classified early/late by the 30-day rule for reporting.

### W9. Reintervention
**Actor:** Surgeon (or interventionalist). **Trigger:** complication treatment or planned maintenance.
1. From access page: "Record procedure" → type (angioplasty, stent, surgical revision, surgical/endovascular thrombectomy, aneurysm repair, banding, DRIL, second-stage transposition, ligation, catheter exchange/reposition, other), date, operator, urgency, anesthesia, technical success, details.
2. Link the complication it treats (`indication_complication`) — pre-selected when launched from a complication's "record treatment" button.
**System:** linked complication auto-updates management/resolution prompts; patency clocks derive automatically (first post-creation procedure ends primary patency — computed, never hand-entered); failed salvage (technical_success = No) prompts abandonment decision.

### W10. Catheter removal after AVF activation
**Actor:** Surgeon; coordinator schedules. **Trigger (automatic):** patient has a bridging TDC **and** the AVF reaches confirmed function (nephrologist confirmation, or N successful two-needle sessions).
1. System creates task "Remove tunneled catheter" on the TDC, due +14 d, and shows a standing banner on the patient timeline: *"Working AVF + catheter in place — catheter day 47."*
2. Surgeon records removal: `AccessProcedure` type `catheter_removal` on the TDC access + `removed_on`, reason `no_longer_needed`.
3. If removal is deliberately deferred (e.g. fragile access), surgeon must enter a documented deferral reason, which snoozes the alert 30 days.
**System:** TDC → `removed`; catheter clock stops; catheter-days feed dashboards. Task escalates to alert at +30 d if ignored.

---

## 6. MVP version (build order)

Everything already implemented (schema, admin, audit trail) plus:

1. **Auth & roles:** login, role-based permissions per §2 matrix incl. row-level rules (nephrologist own-patients, nurse own-center).
2. **Patient timeline page** — the product's core screen: header (identity, status, active accesses with catheter-day counter), chronological event stream (referral, plans, mappings, procedures, complications, session summaries, status events), action buttons per role.
3. **All W1–W10 forms** as dedicated role-aware pages (no reliance on Django admin for clinical users).
4. **Worklists:** new referrals; my tasks (per role); overdue tasks; catheter-in-place list.
5. **Follow-up tasks module (M7):** auto-created tasks per §5, manual tasks, done/deferred with reason.
6. **Alerts, computed on page load** (no background jobs yet): the §10 list evaluated by queries, shown as in-app alert center + banners. Resolution requires a note.
7. **Three dashboards:** service census; creation volume & access-type mix; complications/infection summary (counts, CRBSI per 1000 catheter-days).
8. **Anonymized CSV export** (researcher): patients, accesses, procedures, complications, session aggregates — keyed by `registry_code`, birth year only, no identifiers; every export logged.
9. **Data-quality basics:** duplicate-patient check on registration, required-field completeness indicator per patient.

Explicitly *out* of MVP: email/SMS, KM curves, attachments, Georgian UI, external API, multi-center tenancy.

## 7. Advanced version

1. **Analytics engine:** Kaplan–Meier primary / assisted-primary / secondary patency with correct censoring (death, transplant, transfer, end of study), cumulative infection incidence, per-surgeon and per-center comparisons, KDOQI benchmark panel (e.g. % prevalent patients catheter-only, fistula share).
2. **Background alert engine:** nightly rule evaluation, email digests, urgent same-day email/SMS for infections; per-user notification preferences.
3. **Attachments:** duplex images/reports, operative photos, scanned consents on mapping/procedure/complication records.
4. **Georgian localization:** full ka/en UI (schema already stores language-neutral codes).
5. **Coded refinements:** structured "reason for catheter" field, stenosis location coding, flow-volume (mL/min) surveillance fields on session logs.
6. **External dialysis-center portal hardening:** center-scoped accounts self-served by coordinator, center performance feedback dashboards.
7. **Research workbench:** cohort builder (filter by period, access type, comorbidity), REDCap-compatible export, statistical summary downloads.
8. **API & interoperability:** read-only FHIR-flavored API for national eHealth integration; import of referral demographics.
9. **Multi-center tenancy** if other Georgian services join: center field on patients/users, cross-center aggregate reporting.
10. **Patient-facing lite:** SMS appointment and maturation-check reminders (no portal login in scope).

---

## 8. Page list

| # | Page | URL sketch | Purpose | Roles |
|---|---|---|---|---|
| P1 | Login | `/login/` | Auth | all |
| P2 | Home / worklist | `/` | Role-specific tasks, alerts, shortcuts | all |
| P3 | Patient list & search | `/patients/` | Search by name/registry code/national ID; filters (status, center, surgeon) | surgeon, neph (own), coord |
| P4 | New patient | `/patients/new/` | W1 with duplicate check | surgeon, coord |
| P5 | **Patient timeline** | `/patients/<code>/` | Longitudinal record + actions (core screen) | surgeon, neph (own), coord; nurse (reduced view) |
| P6 | Patient edit | `/patients/<code>/edit/` | Demographics/referral/comorbidity update | surgeon, coord |
| P7 | Status event form | `/patients/<code>/status/new/` | Death/transplant/transfer/LTFU | surgeon, neph (own), coord |
| P8 | Mapping form | `/patients/<code>/mapping/new/` | W3 | surgeon, coord |
| P9 | Plan form | `/patients/<code>/plan/new/` | W2 | surgeon |
| P10 | New access | `/patients/<code>/access/new/` | W4 / W5 (type-adaptive form) | surgeon (+coord for admin fields) |
| P11 | Access detail | `/access/<id>/` | Milestones, procedures, complications, session history, patency summary | surgeon, neph (own), coord; nurse (reduced) |
| P12 | Procedure form | `/access/<id>/procedure/new/` | W9 (and creation edit) | surgeon |
| P13 | Complication form | `/access/<id>/complication/new/` | W8 | surgeon, neph (own), nurse (report), coord |
| P14 | Session log form | `/access/<id>/session/new/` | W7, mobile-friendly | nurse |
| P15 | Catheter removal | `/access/<id>/remove/` | W10 guided form | surgeon |
| P16 | Maturation assessment | `/access/<id>/maturation/` | W6 outcomes form | surgeon |
| P17 | Tasks | `/tasks/` | Filterable worklist, mine/overdue/all | surgeon, coord, neph (own) |
| P18 | Alert center | `/alerts/` | Active alerts, resolve with note | surgeon, coord; nurse (center subset) |
| P19 | Dashboards index + each dashboard | `/dashboards/…` | §9 | per §9 |
| P20 | Export | `/research/export/` | Anonymized CSV bundles + export log | researcher |
| P21 | Audit log browser | `/audit/` | Filter by patient/user/date | surgeon, coord |
| P22 | Nurse center list | `/center/patients/` | Center-scoped patients + "log session" | nurse |
| P23 | Admin (Django) | `/admin/` | Users, thresholds, corrections | superuser |

---

## 9. Dashboard list

| # | Dashboard | Key content | Primary audience |
|---|---|---|---|
| D1 | Service census | Active patients by pathway status; access-in-use mix (AVF/AVG/catheter %); catheter-only patients count (headline KPI); new referrals this month | Surgeon, coordinator |
| D2 | Creation activity | Procedures per month by access type, side, surgeon; technical success rate; planned-vs-performed conversion time | Surgeon |
| D3 | Maturation & cannulation | Maturation rate by type; median days creation→maturation and creation→first successful cannulation; nonmaturation rate; % cannulated ≤ 8 weeks | Surgeon |
| D4 | Patency (advanced: KM curves; MVP: point rates) | Primary / assisted-primary / secondary patency at 6/12/24 months by access type; censoring correctly handled | Surgeon, researcher |
| D5 | Complications & infection | Complication counts by type; early-thrombosis rate; CRBSI + exit-site + tunnel infections per 1000 catheter-days; infection by access type | Surgeon, nephrologist |
| D6 | Catheter dependence | Prevalent % on catheter; median catheter-days before permanent access use; TDCs > 90 days with working AVF; temp catheters > 14 days | Surgeon, coordinator, nephrology lead |
| D7 | Reintervention burden | Interventions per access-year by type; salvage success rate; time to first reintervention | Surgeon, researcher |
| D8 | Data quality & operations | Overdue tasks by assignee; patients with incomplete required fields; accesses in use with no session log 30 d; export activity | Coordinator |

D1–D3 + D5 (counts) and D8 ship in MVP; D4 curves and per-1000-days precision in advanced.

---

## 10. Alert list

Severity: 🔴 same-day action · 🟠 this week · 🟡 housekeeping. MVP = in-app; advanced adds email/SMS for 🔴.

| Code | Trigger (rule, evaluated by query) | Recipient | Sev |
|---|---|---|---|
| A1 | New complication of infection type (CRBSI / exit-site / tunnel / access-site) reported | Responsible surgeon | 🔴 |
| A2 | Nurse-reported complication or `suspected_infection` session problem awaiting surgeon triage > 24 h | Responsible surgeon | 🔴 |
| A3 | Access thrombosis reported, no treatment procedure within 48 h | Responsible surgeon | 🔴 |
| A4 | 2-week check: thrill/bruit absent | Responsible surgeon | 🔴 |
| A5 | AVF `maturing` with no maturation assessment by day 42 (configurable) | Surgeon + coordinator | 🟠 |
| A6 | AVF `ready` but not cannulated within 21 d of readiness | Coordinator (chase dialysis center) | 🟠 |
| A7 | ≥ 2 failed cannulations, or Qb < 250 mL/min ×2 consecutive, or rising venous pressure trend on one access | Responsible surgeon | 🟠 |
| A8 | Temporary (non-cuffed) catheter in place > 14 d | Surgeon + coordinator | 🟠 |
| A9 | TDC still in place ≥ 14 d after AVF confirmed functioning (W10) | Surgeon + coordinator | 🟠 |
| A10 | Catheter-only patient (on HD, no fistula/graft maturing or in use) with no `AccessPlan` in `planned` | Surgeon | 🟠 |
| A11 | New referral with no access plan within 14 d | Surgeon | 🟠 |
| A12 | Predialysis patient with plan but no creation procedure within 60 d | Coordinator | 🟡 |
| A13 | In-use access with no dialysis session log for 30 d (data gap) | Coordinator → nurse's center | 🟡 |
| A14 | Follow-up task overdue > 7 d | Assignee + coordinator | 🟡 |
| A15 | ≥ N successful sessions logged but nephrologist confirmation missing (default N=6) | Responsible nephrologist | 🟡 |

Every alert: link to the patient/access, dismissible only with a resolution note, all resolutions audited.

---

## 11. Data-entry responsibilities by role

| Role | Enters | When | Typical time |
|---|---|---|---|
| **Registry coordinator** | Patient registration (W1); status events from phone/records follow-up; mapping transcription; scheduling fields; task management; data-quality fixes | Referral day; continuously | 10 min/patient registration; daily worklist review |
| **Vascular surgeon** | Access plans (W2); mapping (W3, if self-performed); access creation + index procedure (W4/W5); maturation assessments (W6); complication coding (W8); all procedures (W9); catheter removal (W10); abandonment decisions | Same/next day after each clinical event | 3–5 min/procedure form |
| **Dialysis nurse** | Session logs (W7): first cannulations, monthly routine log, every problem session; suspected-complication reports | At the machine or end of shift | 1–2 min/log |
| **Nephrologist** | Dialysis-use confirmation (one click + date); comments/clinical notes; status events they learn first (death, transplant listing); referral data corrections for own patients | On notification / monthly review of own list | < 5 min/week |
| **Researcher** | Nothing clinical. Runs exports; defines cohort queries (advanced) | Per study | — |
| **Superuser** | User accounts, role assignment, threshold settings (maturation deadline, session-N, catheter-day limits) | Rare | — |

Principle: **whoever generates the clinical fact records it, within 48 h; the coordinator guarantees completeness, not correctness of clinical judgment.**

---

## 12. Research questions the registry should answer

Cohort/endpoint definitions all derive from stored fields — no chart review.

**Patency & durability**
1. Primary, assisted-primary and secondary patency at 6/12/24 months, by access type (radiocephalic vs brachiocephalic vs basilic transposition vs AVG vs HeRO).
2. Time to first reintervention and interventions per access-year, by type.
3. Early thrombosis (≤ 30 d) incidence and its predictors (vessel diameters, diabetes, age, sex, urgency, anticoagulation).

**Maturation**
4. Nonmaturation rate by access type and by preoperative vein/artery diameter thresholds — does the service's 2.0 mm cephalic cut-off predict outcome?
5. Median time creation → maturation and creation → first successful cannulation; effect of salvage procedures on eventual usability.

**Catheter burden & infection**
6. Catheter-days per incident HD patient before permanent access use; proportion of "crash starts" (HD started on catheter with no prior referral).
7. CRBSI, exit-site and tunnel infection rates per 1000 catheter-days; TDC vs temporary catheter comparison.
8. Effect of predialysis referral timing (referral ≥ 6 months before dialysis start vs later) on catheter-only starts and first-year access outcomes.

**Strategy & service performance**
9. Distal-first strategy audit: what fraction of first accesses are radiocephalic, and how do their outcomes compare with upper-arm first?
10. AVG vs AVF in patients with marginal veins: patency, infection, reintervention burden.
11. Access abandonment causes distribution and median functional access lifespan.
12. Per-surgeon and per-dialysis-center outcome variation (risk-adjusted in advanced version).

**Population outcomes**
13. Patient survival on HD by access type in use at 90 days (catheter vs fistula), acknowledging confounding.
14. Pathway attrition: proportion of referred CKD 4–5 patients who die, transplant or transfer before ever needing/receiving an access.

---

## 13. Configurable thresholds (single settings table, superuser-editable)

| Setting | Default |
|---|---|
| Maturation assessment deadline | 42 days |
| Nonmaturation decision point | 84 days |
| Early thrombosis window | 30 days (fixed for reporting comparability) |
| Successful sessions before nephrologist confirmation prompt | 6 |
| TDC removal alert after AVF confirmation | 14 days |
| Temporary catheter dwell alert | 14 days |
| Session-log gap alert | 30 days |
| Low-Qb alert threshold | 250 mL/min ×2 |
