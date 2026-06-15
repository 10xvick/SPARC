# Role Groups — Option B Design

## Motivation

Some KPIs currently set to `All` in `Roles.csv` are only meaningful for developer-type roles.
This design adds a **named role group** mechanism so such KPIs can target a defined subset of
roles while remaining a single row in `Roles.csv` and requiring no hardcoded role lists in
application code.

---

## How It Works

1. A new config file `config/role_groups.json` maps group names → list of member roles.
2. Roles.csv `Role` column accepts a group name (e.g., `Developer Group`) in addition to
   existing values (`All`, `Common`, a specific role name).
3. The applicability check in each dashboard extends to resolve group membership.
4. Scoring assigns a new `Group` role_type / role_specificity value so group KPIs are
   weighted appropriately (below `All`, above `Other` for individuals; `non_specific` for
   team/scrum aggregation).

---

## Files to Create / Modify

### 1. `config/role_groups.json` *(new file)*

```json
{
  "Developer Group": [
    "Developer",
    "Lead Developer",
    "Full Stack Developer",
    "Frontend Engineer",
    "Backend Engineer",
    "Web Developer",
    "Mobile Developer",
    "IoT Developer",
    "Junior Software Engineer",
    "Software Engineer",
    "Sr Software Engineer",
    "Embedded Software Engineer",
    "Developer - Research",
    "Developer - Support phase",
    "Data Engineer",
    "Data Scientist"
  ]
}
```

Additional groups (e.g., `"QA Group"`, `"Lead Group"`) can be added here without any code
change.

---

### 2. `config/scoring_config.json`

Add `"Group"` to the `role_weights` object.  Default weight: **8** (between `All`=5 and
`Secondary`=10 — more targeted than All, less authoritative than an explicit secondary role).
This value is user-configurable via `PUT /api/score-config` the same way as other role weights.

```json
"role_weights": {
  "Primary": 20.0,
  "Secondary": 10.0,
  "Group": 8.0,
  "All": 5.0,
  "Common": 3.0,
  "Other": 1.0
}
```

Update `formula` string to include `Group=8.0`.

---

### 3. `dashboard/backend/app/services/scoring_service.py`

**a) `_load_config` defaults dict** — add `'Group': 8.0` to both the loaded and fallback
`role_weights` dicts.

**b) `save_config` validation** — change the required set and allow weight range 0–20:

```python
# Before
required_role_weights = {'Primary', 'Secondary', 'All', 'Common', 'Other'}

# After
required_role_weights = {'Primary', 'Secondary', 'Group', 'All', 'Common', 'Other'}
```

**c) `formula` string** — add `Group=8.0` to the individual role weights description.

---

### 4. New helper — load role groups

Add a shared utility (or load inline in each dashboard) to read `role_groups.json` once at
module level and expose an `is_in_group(role, kpi_role, role_groups)` helper:

```python
# Suggested location: dashboard/backend/app/services/role_groups_service.py

import json
from pathlib import Path
from functools import lru_cache

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent.parent

@lru_cache(maxsize=1)
def load_role_groups() -> dict:
    path = PROJECT_ROOT / "config" / "role_groups.json"
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def resolve_role_type(kpi_role: str, primary_role: str, secondary_role: str) -> str:
    """Return role_type string for individual scoring."""
    if kpi_role == primary_role:
        return 'Primary'
    if kpi_role == secondary_role:
        return 'Secondary'
    if kpi_role == 'All':
        return 'All'
    if kpi_role == 'Common':
        return 'Common'
    groups = load_role_groups()
    if primary_role in groups.get(kpi_role, []) or secondary_role in groups.get(kpi_role, []):
        return 'Group'
    return 'Other'

def is_applicable(kpi_role: str, primary_role: str, secondary_role: str) -> bool:
    """Return True if the KPI applies to a member with the given roles."""
    if kpi_role in (primary_role, secondary_role):
        return True
    if kpi_role in ('All', 'Common'):
        return True
    groups = load_role_groups()
    return (
        primary_role in groups.get(kpi_role, []) or
        secondary_role in groups.get(kpi_role, [])
    )

def role_specificity(kpi_role: str) -> str:
    """Return role_specificity for team/scrum scoring."""
    if kpi_role in ('All', 'Common', 'Other'):
        return 'non_specific'
    groups = load_role_groups()
    if kpi_role in groups:
        return 'non_specific'   # group KPIs are broad, not role-specific
    return 'specific'
```

---

### 5. `dashboard/backend/app/api/employee_dashboard.py`

**a) Role-match filter** (line ~279) — replace the mask:

```python
# Before
role_match_mask = (
    (roles_df['Role'] == primary_role) |
    (roles_df['Role'] == secondary_role) |
    (roles_df['Role'] == 'All') |
    (roles_df['Role'] == 'Common')
)

# After
from app.services.role_groups_service import load_role_groups
role_groups = load_role_groups()
group_roles_for_employee = {
    g for g, members in role_groups.items()
    if primary_role in members or secondary_role in members
}
role_match_mask = (
    (roles_df['Role'] == primary_role) |
    (roles_df['Role'] == secondary_role) |
    (roles_df['Role'] == 'All') |
    (roles_df['Role'] == 'Common') |
    (roles_df['Role'].isin(group_roles_for_employee))
)
```

**b) role_type assignment** (line ~320) — replace the if/elif block:

```python
# Before
if kpi_role == primary_role:
    role_type = 'Primary'
elif kpi_role == secondary_role:
    role_type = 'Secondary'
elif kpi_role == 'All':
    role_type = 'All'
elif kpi_role == 'Common':
    role_type = 'Common'
else:
    role_type = 'Other'

# After
from app.services.role_groups_service import resolve_role_type
role_type = resolve_role_type(kpi_role, primary_role, secondary_role)
```

---

### 6. `dashboard/backend/app/api/team_dashboard.py`

**a) `is_applicable` check** (inside `aggregate_team_kpis` loop, ~line 183):

```python
# Before
is_applicable = (
    kpi_role == primary_role or
    kpi_role == secondary_role or
    kpi_role in ['All', 'Common']
)

# After
from app.services.role_groups_service import is_applicable as _is_applicable
is_applicable = _is_applicable(kpi_role, primary_role, secondary_role)
```

**b) `role_specificity` field** (in kpi_entry dict, ~line 260):

```python
# Before
"role_specificity": "non_specific" if kpi_role in ('All', 'Common', 'Other') else "specific",

# After
from app.services.role_groups_service import role_specificity as _role_specificity
"role_specificity": _role_specificity(kpi_role),
```

*(Same change applies to the security-scan not_configured kpi_entry block.)*

---

### 7. `dashboard/backend/app/api/scrum_dashboard.py`

Identical changes to team_dashboard.py — same two locations in `aggregate_scrum_kpis`.

---

### 8. `dashboard/backend/app/api/reports.py` — `role-kpi-applicability` endpoint

The `_get_shared_role_buckets` helper (or equivalent) that builds the `applied_role_buckets`
list for a given role currently only adds `All`, `Common`, `Metric` etc.  It should also add
any group names that include the selected role:

```python
from app.services.role_groups_service import load_role_groups

def _get_shared_role_buckets(roles_df, selected_role: str = None) -> list:
    buckets = ['Common', 'All', ...]   # existing logic
    if selected_role:
        groups = load_role_groups()
        for group_name, members in groups.items():
            if selected_role in members:
                buckets.append(group_name)
    return buckets
```

---

## Roles.csv Change (example)

To restrict a KPI that is currently `All` to developer-type roles only, change its `Role`
column value:

```
Before:  k42,All,Code commits per week,...
After:   k42,Developer Group,Code commits per week,...
```

No other column changes required.

---

## 9. Backend API — Role Groups CRUD

New router: `dashboard/backend/app/api/role_groups.py`  
Mount under: `GET|POST|PUT|DELETE /api/role-groups`

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/role-groups` | Return full `role_groups.json` content |
| `POST` | `/api/role-groups` | Create a new group `{ name, roles[] }` |
| `PUT` | `/api/role-groups/{group_name}` | Replace member list for an existing group |
| `DELETE` | `/api/role-groups/{group_name}` | Remove a group entirely |
| `GET` | `/api/role-groups/available-roles` | Return list of all unique roles from `Roles.csv` (for the role picker) |

All write operations must:
1. Validate that each role name exists in `Roles.csv` before saving.
2. Write atomically to `config/role_groups.json` (write → temp file → rename).
3. Invalidate the `lru_cache` on `role_groups_service.load_role_groups` so the running
   backend picks up the change without a restart.
4. Require `Admin` role (use existing `require_admin` dependency).

---

## 10. Frontend — Role Groups Management Page

### Placement in existing navigation

The **TeamSight Users & Roles** section in `ConfigurationPage.tsx` currently has two sub-tabs
under the _TeamSight Users & Roles_ main tab:

```
Configuration Management
  └── TeamSight Users & Roles      ← mainTab index 0
        ├── Employee Management    ← teamSightTab index 0  (EmployeeManagementPage)
        └── Role & KPI Management  ← teamSightTab index 1  (RoleManagementPage)
```

Add a **third** sub-tab:

```
Configuration Management
  └── TeamSight Users & Roles
        ├── Employee Management    ← index 0
        ├── Role & KPI Management  ← index 1
        └── Role Groups            ← index 2  (RoleGroupsPage)  ← NEW
```

**Files to change for navigation:**
- `dashboard/frontend/src/pages/ConfigurationPage.tsx` — add a third `<Tab>` and
  `<SubTabPanel>` for `RoleGroupsPage` inside the `teamSightTab` section.
- `dashboard/frontend/src/pages/TeamSightUsersRolesPage.tsx` — same: add third tab entry
  (this page mirrors the sub-tab structure independently of `ConfigurationPage`).
- `dashboard/frontend/src/routes.tsx` — add route `config/teamsight/role-groups` pointing to
  `RoleGroupsPage` with `requiredPermissions={['view:config']}`.

---

**File:** `dashboard/frontend/src/pages/RoleGroupsPage.tsx`  
**Route:** `/config/teamsight/role-groups` (also embedded as sub-tab index 2)  
**Access:** Visible to all; edit/create/delete restricted to Admin (hide action buttons for non-admin)

### Page Layout

```
┌─────────────────────────────────────────────────────┐
│  Role Groups                            [+ New Group]│
│  ─────────────────────────────────────────────────  │
│  ┌──────────────────────────────────────────────┐   │
│  │ Developer Group                    16 roles   │   │
│  │  [Developer] [Lead Developer] [Full Stack…]   │   │
│  │  [+ 13 more]                   [Edit][Delete] │   │
│  └──────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────┐   │
│  │ QA Group                            4 roles   │   │
│  │  [QA Engineer] [Lead Tester] [Sr Integration] │   │
│  │  [Test Engineer]               [Edit][Delete] │   │
│  └──────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────┘
```

### Components

**Group Card** (read mode)
- Group name as heading with role count badge
- Member roles displayed as `<Chip>` tags (max 5 visible; remainder collapsed under `[+N more]`)
- **Edit** icon button → opens Edit Dialog (Admin only; hidden for non-admin)
- **Delete** icon button → confirmation dialog before `DELETE /api/role-groups/{name}` (Admin only)

**Create / Edit Dialog**
- Text field: Group Name (disabled in edit mode)
- Searchable checkbox list: Available Roles (from `GET /api/role-groups/available-roles`,
  which reads unique role names from `Roles.csv`)
- Currently selected roles shown as removable `<Chip>` tags above the list
- **Save** / **Cancel** buttons
- Inline validation: group name required; at least one role required; name must be unique (create)
- Success/error snackbar on save

**Confirmation Dialog** (delete)
- Warns: _"Deleting this group will cause any KPIs assigned to '[group name]' in Roles.csv
  to fall back to 'Other' applicability until Roles.csv is updated."_

### API client (new file: `dashboard/frontend/src/services/roleGroupsApi.ts`)

```typescript
getRoleGroups(): Promise<Record<string, string[]>>
getAvailableRoles(): Promise<string[]>
createRoleGroup(name: string, roles: string[]): Promise<void>
updateRoleGroup(name: string, roles: string[]): Promise<void>
deleteRoleGroup(name: string): Promise<void>
```

### UX Notes
- After any save/delete, re-fetch the full group list to reflect changes.
- Show an info banner: _"Changes take effect immediately — no backend restart required."_
- Non-admin users see cards in read-only mode (no Edit/Delete/New Group buttons rendered).
- Role chips use the same MUI `<Chip>` style as elsewhere in the app for visual consistency.

---

## Backward Compatibility

- Existing `All`, `Common`, specific role rows are completely unaffected.
- If `role_groups.json` is missing or empty, all group checks fall through to `Other` /
  `specific`, preserving current behaviour.
- Write operations via the API invalidate the `lru_cache`, so the backend reflects changes
  immediately without a restart.

---

## Implementation Checklist

**Config & Service Layer**
- [ ] Create `config/role_groups.json` with initial `Developer Group`
- [ ] Update `config/scoring_config.json` — add `"Group": 8.0` to `role_weights`; update `formula` string
- [ ] Create `dashboard/backend/app/services/role_groups_service.py`
- [ ] Update `dashboard/backend/app/services/scoring_service.py` — add Group to validation

**Backend — Applicability Logic**
- [ ] Update `dashboard/backend/app/api/employee_dashboard.py` — 2 locations
- [ ] Update `dashboard/backend/app/api/team_dashboard.py` — 2 locations
- [ ] Update `dashboard/backend/app/api/scrum_dashboard.py` — 2 locations
- [ ] Update `dashboard/backend/app/api/reports.py` — role-kpi-applicability endpoint

**Backend — Role Groups API**
- [ ] Create `dashboard/backend/app/api/role_groups.py` (CRUD endpoints)
- [ ] Mount router in `main.py`
- [ ] Add cache-invalidation call in write endpoints (`load_role_groups.cache_clear()`)

**Frontend — Role Groups Management Page**
- [ ] Create `dashboard/frontend/src/pages/RoleGroupsPage.tsx`
- [ ] Create `dashboard/frontend/src/services/roleGroupsApi.ts`
- [ ] Add third sub-tab in `dashboard/frontend/src/pages/ConfigurationPage.tsx`
- [ ] Add third sub-tab in `dashboard/frontend/src/pages/TeamSightUsersRolesPage.tsx`
- [ ] Add route `config/teamsight/role-groups` in `dashboard/frontend/src/routes.tsx`

**Data**
- [ ] Update `config/Roles.csv` — change target KPI rows from `All` → group name

**Validation**
- [ ] Restart backend and validate scoring on employee/scrum/team dashboards
- [ ] Test create/edit/delete from the UI page
- [ ] Verify cache invalidation (change a group in UI, reload a dashboard — no restart needed)
