# Fetch Cutoff And Fiscal Calendar TODO

## Purpose

Document the planned separation between:

1. Data fetch bootstrap/history cutoff dates used by ingestion jobs
2. Fiscal calendar settings used by KPI annual/quarterly computation and dashboard target/proration logic

This is a design/TODO document only. No implementation is included here.

## Status

- Current status: Documentation updated only
- Code changes: Not started
- UI/API implementation: Deferred to a later task

## Problem

The codebase currently mixes two different concepts:

- Historical fetch boundary for JIRA, GitHub, and Copilot ingestion
- Fiscal year start used for KPI `Year`, `Quarter`, annual values, and dashboard prorated target comparison

Today these are effectively coupled through values such as:

- `cutoffDate = 2025-03-31`
- `fiscal_start_month = 4`

That coupling makes future changes risky because a fetch-history decision can unintentionally affect KPI year logic, or vice versa.

## Desired Behavior

### Data Fetch

Fetch jobs should continue to use an older bootstrap date for first-load/full-history ingestion.

Examples:

- JIRA fetch should keep its configured historical cutoff/start date
- GitHub fetch should keep its configured historical cutoff/start date
- Copilot metrics fetch should keep its configured historical cutoff/start date

These settings should control ingestion only.

### KPI And Dashboard Calendar

KPI annual values, fiscal year labels, quarter labels, annual target comparisons, and prorated target logic should use the currently configured fiscal year start.

Example:

- If fiscal year starts in April, KPI annual calculations use April-March regardless of how far back fetch jobs load data

## Proposed Single-Place Configuration

Introduce one central configuration file with two distinct sections.

Suggested file:

- `config/time_config.json`

## Admin UI Requirement

These parameters must be configurable from:

- `System Admin -> Scoring & Thresholds`

in a dedicated, separate section (not mixed into the existing scoring sliders).

The section should expose both groups of settings:

1. Data fetch cutoff settings
2. KPI fiscal calendar settings

The section must also show clear warnings that:

- changing values can affect historical ingestion windows and KPI period interpretation
- running processes may require backend restart before new values are fully reflected

Suggested shape:

```json
{
  "data_fetch": {
    "bootstrap_start_date": "2025-04-01",
    "jira_bootstrap_start_date": "2025-04-01",
    "github_bootstrap_start_date": "2025-04-01",
    "copilot_bootstrap_start_date": "2025-04-01"
  },
  "kpi_calendar": {
    "fiscal_start_month": 4,
    "fiscal_start_day": 1
  }
}
```

## Configuration Semantics

### `data_fetch.bootstrap_start_date`

Default oldest date to use when a fetch job performs first-time bootstrap or a full-history reload.

### `data_fetch.jira_bootstrap_start_date`

Optional JIRA-specific override.

### `data_fetch.github_bootstrap_start_date`

Optional GitHub-specific override.

### `data_fetch.copilot_bootstrap_start_date`

Optional Copilot-specific override.

### `kpi_calendar.fiscal_start_month`

Month at which the fiscal year starts.

### `kpi_calendar.fiscal_start_day`

Day within that month at which the fiscal year starts. If not needed, this can remain `1` permanently.

## Recommended Usage Rules

### Fetch Jobs Must Use Only `data_fetch`

The following logic should read bootstrap/history cutoff values only from the `data_fetch` section:

- JIRA fetch bootstrapping/full fetch
- GitHub fetch bootstrapping/full fetch
- Copilot metrics annual/bootstrap ingestion

### KPI And Dashboard Logic Must Use Only `kpi_calendar`

The following logic should read fiscal calendar values only from the `kpi_calendar` section:

- KPI `Year` label generation
- KPI `Quarter` label generation
- Annual aggregation windows
- Quarterly aggregation windows
- Dashboard prorated target comparison
- Dashboard annual target comparison

## Why This Design

Benefits:

- Separates ingestion history concerns from business calendar concerns
- Prevents accidental KPI changes when historical fetch boundaries are adjusted
- Prevents accidental fetch changes when fiscal calendar changes
- Keeps configuration centralized in one file
- Supports future divergence between data sources without code duplication

## Current High-Priority Impact Points

These areas should be updated first when implementation begins.

### Core config and defaults

- `config/jira_config.json`
- `config/copilot_metrics_config.json`
- `dashboard/backend/app/api/project_config.py`
- `dashboard/frontend/src/pages/ProjectOnboardingPage.tsx`
- `dashboard/frontend/src/components/ScoringConfigPanel.tsx`

### Shared fiscal logic

- `src/kpi_helpers.py`
- `src/KppEvaluator.py`
- `dashboard/backend/app/api/kpi_utils.py`

### Dashboard/API consumers

- `dashboard/backend/app/api/reports.py`
- `dashboard/backend/app/api/team_dashboard.py`
- `dashboard/backend/app/api/scrum_dashboard.py`
- `dashboard/backend/app/api/employee_dashboard.py`

### Fetch jobs

- `src/jira_fetch.py`
- `src/github_fetch.py`
- `src/copilot_metrics_fetch.py`

## Migration Strategy

Recommended phased implementation:

1. Add a new shared loader for `config/time_config.json`
2. Switch fetch jobs to `data_fetch.*`
3. Switch KPI and dashboard logic to `kpi_calendar.*`
4. Keep old `cutoffDate` values as temporary fallback for backward compatibility
5. Validate generated KPI `Year` and `Quarter` labels against expected results
6. Validate first-load and incremental fetch behavior for JIRA, GitHub, and Copilot
7. Remove duplicated/default fallback values after successful rollout

## Validation Checklist

When implementation begins, verify the following:

- JIRA full fetch still starts from the intended historical bootstrap date
- GitHub full fetch still starts from the intended historical bootstrap date
- Copilot fetch still starts from the intended historical bootstrap date
- Incremental fetches remain unchanged
- KPI annual values use the configured fiscal calendar
- KPI quarter labels use the configured fiscal calendar
- Dashboard prorated targets use the configured fiscal calendar only
- Existing KPI CSV schema remains unchanged

## Open Decisions

Questions to finalize before implementation:

1. Should `bootstrap_start_date` be mandatory, or optional with per-source overrides only?
2. Should GitHub explicitly expose bootstrap date in UI/config even though it already uses checkpoint-driven incrementals?
3. Should `fiscal_start_day` be retained for future-proofing, or omitted for simplicity if month-level control is sufficient?
4. Should legacy `cutoffDate` fields remain in project onboarding UI as aliases during migration?

## Non-Goals

This TODO does not include:

- Immediate refactoring
- Changes to historical backup copies
- Changes to generated output schema
- Remote deployment steps
