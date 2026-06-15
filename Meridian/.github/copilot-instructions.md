# GitHub Copilot Instructions for TeamSight Project

## Shell Tool Availability

**`rg` (ripgrep) is NOT installed on this machine. Never use `rg` in any terminal command.**

Use standard alternatives instead:
- Text search: `grep -r "pattern" path` or `grep -rn "pattern" path`
- File content search: `grep -r "pattern" path --include="*.py"`
- Recursive search: `grep -rn "pattern" .`

**`fd` is NOT assumed to be installed. Use `find` instead:**
- Find files: `find . -name "*.py"` or `find . -type f -name "*.csv"`

Always prefer POSIX-compatible tools (`grep`, `find`, `awk`, `sed`) that are guaranteed available.

## Remote Server

- **Host:** `root@10.222.2.217`
- **Deployment path:** `/opt/teamsight/teamsight`
- Use `ssh root@10.222.2.217` to connect
- All paths on the remote mirror the local structure under `/opt/teamsight/teamsight/` (e.g., `output/JIRAIssues.csv`, `config/`, `src/`, `dashboard/`, etc.)
- Use `./dashboard/manage.sh` on the remote server the same way as locally

## Code Quality and Error Handling

**FastAPI Best Practices:**
- Use `lifespan` context manager instead of deprecated `@app.on_event("startup")` and `@app.on_event("shutdown")`
- Example:
  ```python
  from contextlib import asynccontextmanager
  
  @asynccontextmanager
  async def lifespan(app: FastAPI):
      # Startup logic
      yield
      # Shutdown logic
  
  app = FastAPI(lifespan=lifespan)
  ```

**ALWAYS fix TypeScript/JavaScript errors before committing:**

1. **Remove unused imports:**
   - Use `get_errors` tool to identify unused imports
   - Remove any imported components, icons, or utilities that aren't used in the code
   - Example: Remove `List`, `ListItem`, `HistoryIcon` if not referenced

2. **Handle "possibly undefined" errors:**
   - Use optional chaining (`?.`) for objects that might be undefined
   - Use nullish coalescing operator (`??`) for fallback values
   - Example: `health?.response_time_ms?.toFixed(0)` instead of `health.response_time_ms.toFixed(0)`
   - Example: `(value ?? defaultValue)` for comparisons

3. **Verify fixes:**
   - Always call `get_errors` after making changes to verify no errors remain
   - Fix all compile errors, not just warnings
   - Ensure TypeScript strict mode compliance

**Common error patterns to fix:**
```typescript
// ❌ Bad: Unused import
import { List, ListItem } from '@mui/material';

// ✅ Good: Only import what's used
import { Container, Box } from '@mui/material';

// ❌ Bad: Possibly undefined
const value = data.field.subfield;

// ✅ Good: Optional chaining
const value = data?.field?.subfield;

// ❌ Bad: Undefined in comparison
if (data.value < 100) { }

// ✅ Good: Nullish coalescing
if ((data?.value ?? 1000) < 100) { }
```

## Remote Deployment Workflow

> **IMPORTANT: Never deploy to the remote server automatically or at the end of a coding task.**
> Always stop after completing local changes and explicitly wait for the user to say "deploy" or "update remote" before running any `scp`, `ssh`, or remote commands.

Follow these steps exactly for every deployment to `root@10.222.2.217`.

### Step 1 — Bump version & build wheel
```bash
# Bump version in setup.py (e.g. 2.0.6 → 2.0.7), then:
rm -rf dist && .venv/bin/python -m build --wheel
# Or use the helper script (auto-bumps version):
echo "y" | ./scripts/build_wheel.sh <version>
```

### Step 2 — Package code-only bundle (default — never overwrites remote data)
```bash
./scripts/package_complete_bundle.sh --no-prompt --target-folder /opt/teamsight/teamsight
BUNDLE=$(ls -1t dist/teamsight-complete-*.tar.gz | head -1)
```

### Step 3 — Copy bundle to remote
```bash
scp "$BUNDLE" root@10.222.2.217:/tmp/
```

### Step 4 — Deploy on remote
```bash
BUNDLE_NAME=$(basename "$BUNDLE")
ssh root@10.222.2.217 "
  mkdir -p /tmp/ts_deploy && \
  tar -xzf /tmp/${BUNDLE_NAME} -C /tmp/ts_deploy && \
  chmod +x /tmp/ts_deploy/scripts/deploy_complete_bundle.sh && \
  /tmp/ts_deploy/scripts/deploy_complete_bundle.sh \
    --bundle /tmp/${BUNDLE_NAME} \
    --target-folder /opt/teamsight/teamsight \
    --no-prompt --install-wheel --start-services
"
```

### Step 4a — Ensure wheel is installed in backend venv
> **Critical:** The backend runs in its own venv, so the wheel **must** be in `/opt/teamsight/teamsight/dashboard/backend/venv/` for version updates to take effect in the API.
```bash
WHEEL=$(ls -1t /opt/teamsight/teamsight/dist/teamsight-*.whl | head -1)
ssh root@10.222.2.217 "
  /opt/teamsight/teamsight/dashboard/backend/venv/bin/python3 -m pip install \
    --no-deps --force-reinstall \"${WHEEL}\"
"
```

### Step 5 — Rebuild frontend on remote (required every time)
> UI is served as static files from port 8000. Port 5173 is NOT open on remote.
```bash
ssh root@10.222.2.217 "cd /opt/teamsight/teamsight/dashboard/frontend && npm run build"
```

### Step 5a — One-shot frontend/dist hardening (prevents stale UI)
> Use this exact sequence when frontend updates are not reflecting after deploy.
```bash
ssh root@10.222.2.217 "
   cd /opt/teamsight/teamsight/dashboard/frontend && \
   rm -rf dist && \
   npm run build && \
   test -f dist/index.html && \
   ls -1 dist/assets/index-*.js | head -1
"
```

**Why this matters:**
- `rm -rf dist` guarantees no stale assets survive from previous builds.
- `test -f dist/index.html` fails fast if build output is incomplete.
- listing `dist/assets/index-*.js` confirms new hashed bundle exists.

### Step 5b — Backend venv wheel reinstall is mandatory
> `deploy_complete_bundle.sh --install-wheel` may report same-version already installed; always force reinstall wheel in backend venv.
```bash
WHEEL=$(ls -1t /opt/teamsight/teamsight/dist/teamsight-*.whl | head -1)
ssh root@10.222.2.217 "
   /opt/teamsight/teamsight/dashboard/backend/venv/bin/python3 -m pip install \
      --no-deps --force-reinstall \"${WHEEL}\"
"
```

### Step 6 — Restart backend on remote
```bash
ssh root@10.222.2.217 "cd /opt/teamsight/teamsight/dashboard && ./manage.sh restart backend"
```

### Step 7 — Verify
```bash
ssh root@10.222.2.217 "cd /opt/teamsight/teamsight/dashboard && ./manage.sh status"
# Check version via API:
curl -s http://10.222.2.217:8000/api/config | grep version
# UI: http://10.222.2.217:8000/
```

### Data migration (when CSV schema changes)
If any `output/k*-data.csv` schema changes on local, migrate the remote file **before** restarting:
```bash
# Example: add SAPID column by joining with Resources.csv
ssh root@10.222.2.217 "python3 - <<'EOF'
import csv, shutil
# ... migration script ...
EOF
"
```
Always backup (`shutil.copy2`) before writing, and verify all rows matched.

## Service Management

**ALWAYS use the `manage.sh` script for service management:**

```bash
# Start services
./dashboard/manage.sh start [backend|frontend|all]

# Stop services
./dashboard/manage.sh stop [backend|frontend|all]

# Restart services
./dashboard/manage.sh restart [backend|frontend|all]

# Check status
./dashboard/manage.sh status

# View logs
./dashboard/manage.sh logs [backend|frontend] [lines]

# Follow logs in real-time
./dashboard/manage.sh follow [backend|frontend]
```

**DO NOT use direct commands like:**
- ❌ `pkill -9 uvicorn`
- ❌ `uvicorn app.main:app --reload`
- ❌ `npm run dev` directly
- ❌ Manual PID management

**Service Details:**
- Backend: FastAPI on port 8000 (Python venv at `dashboard/backend/venv`)
- Frontend: React + Vite on port 5173 (Node.js)
- Logs: `dashboard/logs/backend.log` and `dashboard/logs/frontend.log`
- PIDs: Stored in `dashboard/.pids/`

## Project Structure

```
<installation-folder>/          # TeamSight project root
├── config/                      # Configuration files
│   ├── Resources.csv           # Employee/resource data
│   ├── Roles.csv               # Role definitions with KPIs
│   ├── github_config.json      # GitHub API configuration
│   └── jira_config.json        # JIRA API configuration
├── src/                         # Python KPI evaluation scripts
│   ├── KppEvaluator.py         # KPI orchestrator (27 KPIs)
│   ├── kpp_k*.py               # Individual KPI implementations
│   ├── github_fetch.py         # GitHub data fetcher
│   └── jira_fetch.py           # JIRA data fetcher
├── output/                      # Generated KPI data files
│   ├── k*-data.csv             # Individual KPI results
│   ├── JIRAIssues.csv          # JIRA issues snapshot
│   └── github_commits.csv      # GitHub commits data
├── dashboard/                   # Web dashboard application
│   ├── manage.sh               # **SERVICE MANAGEMENT SCRIPT**
│   ├── backend/                # FastAPI backend
│   │   ├── app/
│   │   │   ├── main.py         # FastAPI application entry
│   │   │   ├── api/            # API endpoints
│   │   │   └── services/       # Business logic (scheduler, etc.)
│   │   └── venv/               # Python virtual environment
│   └── frontend/               # React + TypeScript frontend
│       ├── src/
│       │   ├── pages/          # Dashboard pages
│       │   └── api/            # API client functions
│       └── node_modules/       # Node.js dependencies
└── .venv/                       # Main Python virtual environment
```

## Python Environment Management

**ALWAYS call `configure_python_environment` before:**
- Running any Python commands in terminal
- Installing Python packages
- Getting Python environment details
- Executing Python scripts

**For Python package installation, use:**
```bash
# Correct: Uses the tool which handles venv activation
install_python_packages(packageList=["package-name"])

# Incorrect: Direct pip commands without venv
pip install package-name
```

**Python executables:**
- Main project: `<installation-folder>/.venv/bin/python`
- Dashboard backend: `<installation-folder>/dashboard/backend/venv/bin/python`

## KPI CSV Output Schema (Mandatory)

Every KPI script **must** output these columns in this exact order:

```
CurrentDate,Week,Month,Quarter,Year,SAPID,Name,Weekly,Monthly,Quarterly,Annual
```

- `CurrentDate` — snapshot date string (e.g. `20260329`)
- `Week` — ISO week label (e.g. `202613`)
- `Month` — month label (e.g. `Mar2026`)
- `Quarter` — quarter label (e.g. `JFM2026`)
- `Year` — fiscal year label (e.g. `FY2025`)
- `SAPID` — employee SAPID as a plain integer string (no `.0`) from `Resources.csv`
- `Name` — employee display name exactly as spelled in `Resources.csv`
- `Weekly`, `Monthly`, `Quarterly`, `Annual` — KPI values for each period

**Never omit SAPID.** It is the primary key used for all lookups. Always read SAPID from `Resources.csv` alongside the Name when building the result dataframe.

Template pattern for final column selection:
```python
result_df['SAPID'] = result_df['SAPID'].apply(
    lambda v: str(int(float(str(v).strip()))) if str(v).strip() not in ('', 'nan') else ''
)
final_df = result_df[['Date', 'Week', 'Month', 'Quarter', 'Year', 'SAPID', 'Name',
                       'Weekly', 'Monthly', 'Quarterly', 'Annual']]
final_df = final_df.rename(columns={'Date': 'CurrentDate'})
```

## KPI System

**27 KPIs registered in KppEvaluator.py:**
- Equivalent KPIs mechanism: `k8→k4`, `k20→k16`, `k22→k18`
- Each KPI generates a `k*-data.csv` file in `output/`
- Run all KPIs: `python src/KppEvaluator.py --run-all`
- Run specific KPI: `python src/KppEvaluator.py --kpi k3`
- Describe KPIs: `python src/KppEvaluator.py --describe`

### Adding a New KPI (mandatory checklist)

When adding any new KPI (`kXYZ`), ALWAYS do all of the following:

1. **Create KPI script**
   - Add `src/kpp_kXYZ.py`
   - Keep output schema consistent: `CurrentDate,Week,Month,Quarter,Year,SAPID,Name,Weekly,Monthly,Quarterly,Annual`
   - Write output file as `output/kXYZ-data.csv`

2. **Register in orchestrator**
   - Update `src/KppEvaluator.py`:
     - Add import `from kpp_kXYZ import kXYZ`
     - Add `'kXYZ': kXYZ` in `self.kpi_functions`
     - Add `run_kpi()` dispatch branch with required inputs for the KPI

3. **Add KPI definition row**
   - Update `config/Roles.csv` with new `Index`, `Role`, description, targets, type, and goal type.

4. **Validate and operationalize**
   - Run KPI script once for sanity.
   - Restart backend if `Roles.csv` or `KppEvaluator.py` changed:
     - `./dashboard/manage.sh restart backend`

### Team-level KPI implementation rules

For KPIs computed at team level but assigned to individuals:

- Use **configuration-driven mapping** (no hardcoded project→team mapping in code).
- If multiple mapped sources exist for one team, aggregate per KPI rule (e.g., sum).
- Assign the same team value to all team members from `Resources.csv`.
- Keep CSV format unchanged (no extra columns unless explicitly requested).
- If period behavior is custom (e.g., Monthly/Quarterly/Annual median of weekly values), implement exactly as specified in KPI requirement.

### Typical files to add/modify for team-level KPIs

- Add: `src/kpp_kXYZ.py`
- Modify: `src/KppEvaluator.py`
- Modify: `config/Roles.csv`
- Optional mapping config: `config/security_scan_config.json` (or source-specific config)
- Optional onboarding management:
  - `dashboard/backend/app/api/project_config.py`
  - `dashboard/frontend/src/pages/ProjectOnboardingPage.tsx`

**After adding/modifying KPIs:**
1. Update `src/KppEvaluator.py` to register the KPI
2. Restart backend: `./dashboard/manage.sh restart backend`
3. Test the KPI endpoint in the API

## Backend Restart Requirements

**Restart backend when:**
- ✅ Roles.csv is modified (new roles, KPI assignments)
- ✅ Resources.csv structure changes
- ✅ KppEvaluator.py is modified (new KPIs, equivalent mappings)
- ✅ Backend API code changes (sometimes auto-reloads, but restart if issues)

**Use:** `./dashboard/manage.sh restart backend`

## Dashboard Navigation

**Dashboard hierarchy:**
- Team Dashboard → Scrum Dashboard → Employee Dashboard
- URL parameters: `?team=X`, `?scrum=Y`, `?name=Z`
- All drill-down links are functional

**Key pages:**
- Admin Page: Job scheduling, service management, health checks
- Team Dashboard: Aggregated team KPIs, scrum lists, member details
- Scrum Dashboard: Scrum-level aggregated KPIs
- Employee Dashboard: Individual employee KPI performance

## Role-Based KPI Evaluation

**KPI applicability rules (in order):**
1. Check if role matches Primary Role in Resources.csv
2. Check if role matches Secondary Role in Resources.csv
3. Check if role is "All" (applies to everyone)
4. Check if role matches "Common" group type

**Only count members where KPI is applicable based on above rules.**

## Data Files

**Resources.csv (165 resources):**
- Columns: Ref, Name, SAPID, Team, Primary Role, Secondary Role, Scrum, etc.
- Role names standardized: Developer, DevOps Engineer, QA Engineer, UI Developer, UI Designer

**Roles.csv (298 rows, 169 unique KPI definitions):**
- 110 legacy rows + 30 new role KPIs added
- New roles: Data Engineer, Data Scientist, Development Manager, Lead Data Scientist, Lead Developer, Lead Tester, Offshore Lead, Splunk Architect, Support, Web Developer
- Columns: Index (KPI ID), Role, KPP Goals, Measurement Criteria, Tool, Measure, Type, Aggregation Type, Weekly/Quarterly/Annual Target, Goal Type

## Recent Changes Summary

**Latest updates (March 10, 2026):**
1. ✅ Standardized role names in Resources.csv:
   - Python Developer → Developer (5 resources)
   - QA, Tester → QA Engineer (7 resources)
   - Devops → DevOps Engineer (3 resources)
   - UI designer, UX/UI Designer → UI Designer (3 resources)
   - UI developer → UI Developer (1 resource)

2. ✅ Added 10 new roles to Roles.csv (k269-k298):
   - Data Engineer (k269-k271): Feature implementation, code quality, query performance
   - Data Scientist (k272-k274): Feature implementation, code quality, research technologies
   - Development Manager (k275-k277): Strategic planning, team performance, stakeholder management
   - Lead Data Scientist (k278-k280): Code review, project delivery, research technologies
   - Lead Developer (k281-k283): Code review, project delivery, architecture
   - Lead Tester (k284-k287): Code review, bug identification, automation, test documentation
   - Offshore Lead (k288-k290): Code review, project delivery, team coordination
   - Splunk Architect (k291-k293): Architecture, technical documentation, system performance
   - Support (k294-k295): Incident resolution time, customer satisfaction
   - Web Developer (k296-k298): Code quality, UI development, user experience

3. ✅ Backend restarted successfully (PID: 36856)
4. ✅ Frontend running (PID: 82230)

## Git Workflow (if needed)

When making commits, provide clear, structured commit messages:
```
feat: Add Data Engineer role with query performance KPIs
fix: Standardize role names in Resources.csv
chore: Restart backend to load new role definitions
```

## Debugging

**Check service status:**
```bash
./dashboard/manage.sh status
```

**View recent logs:**
```bash
./dashboard/manage.sh logs backend 100
./dashboard/manage.sh logs frontend 100
```

**Follow logs in real-time:**
```bash
./dashboard/manage.sh follow backend
```

**Common issues:**
- Port already in use: `./dashboard/manage.sh restart backend` (auto-cleans ports)
- Module not found: Check if backend restarted after code changes
- Data not loading: Verify CSV files in `config/` and `output/` directories

## Remember

1. **Always use manage.sh for service management**
2. **Always configure Python environment before running Python commands**
3. **Backend requires restart after Roles.csv or KppEvaluator.py changes**
4. **27 KPIs total, 3 are equivalent (share computation)**
5. **Role-based filtering: Primary → Secondary → All → Common**
