# CI/CD Pipeline Documentation

## Overview

Two GitHub Actions workflows handle the build and deployment lifecycle:

| Workflow | File | Trigger |
|---|---|---|
| CI - Build | `ci.yml` | Every push to any branch / PR to `main` |
| CD - Deploy | `deploy.yml` | Manual only (`workflow_dispatch`) |

**Runner:** Both workflows run on the `self-hosted` runner (`ubuntu-runner1`) hosted on AWS within the organization's GitHub Enterprise environment (`github01.hclpnp.com`).

---

## CI Pipeline (`ci.yml`)

Validates every code change builds and packages cleanly. No deployment occurs.

### Trigger
- Push to any branch
- Pull request targeting `main`

### Steps

| # | Step | What it does |
|---|---|---|
| 1 | Checkout code | Pulls the pushed branch onto the runner |
| 2 | Set up Python 3.11 | Ensures Python 3.11 is available (cached on runner) |
| 3 | Install build tools | `pip install build wheel setuptools` |
| 4 | Build Python wheel | `python -m build --wheel` → produces `dist/teamsight-<version>-py3-none-any.whl` |
| 5 | Set up Node.js 20 | Ensures Node.js 20 is available (cached on runner) |
| 6 | Install frontend dependencies | `npm ci` using committed `package-lock.json` for exact reproducible installs |
| 7 | Type-check frontend | `tsc --noEmit` — validates TypeScript compiles without errors |
| 8 | Package deployment bundle | Runs `scripts/package_complete_bundle.sh` → produces `dist/teamsight-complete-<timestamp>.tar.gz` |
| 9 | Upload bundle artifact | Uploads `.tar.gz` to GHE as a workflow artifact (retained 7 days, `upload-artifact@v3`) |

### Notes
- `upload-artifact@v3` is used (not v4) — v4+ is not supported on GHES.
- The bundle excludes: `node_modules/`, backend `venv/`, `config/`, `output/`, `data/` (runtime data stays on server).

---

## CD Pipeline (`deploy.yml`)

Builds from source and deploys to the production server. **Never runs automatically.**

### Trigger
- Manual only: Actions tab → "CD - Deploy" → "Run workflow"
- Optional `run_id` input (informational, for traceability)
- Uses `environment: production` (can be configured for approval gates in GHE settings)

### Required Secrets

Set these in GHE: `Settings → Secrets and variables → Actions`

| Secret | Description |
|---|---|
| `SSH_PRIVATE_KEY` | Private key for SSH access to the production server |
| `REMOTE_HOST` | IP or hostname of the production server |
| `REMOTE_USER` | SSH login user on the production server |

See `.secrets.example` for the template. The live `.secrets` file is gitignored.

### Steps

#### Build phase (on runner)

| # | Step | What it does |
|---|---|---|
| 1 | Checkout code | Pulls branch onto runner |
| 2 | Set up Python 3.11 | Ensures Python 3.11 available |
| 3 | Install build tools | `pip install build wheel setuptools` |
| 4 | Build Python wheel | `python -m build --wheel` |
| 5 | Set up Node.js 20 | Ensures Node.js 20 available |
| 6 | Install frontend dependencies | `npm ci` |
| 7 | Type-check frontend | `tsc --noEmit` |
| 8 | Package deployment bundle | `scripts/package_complete_bundle.sh` → `.tar.gz` in `dist/` |

#### SSH setup (runner → production server)

| # | Step | What it does |
|---|---|---|
| 9 | Set up SSH agent | Loads `SSH_PRIVATE_KEY` secret into runner's SSH agent |
| 10 | Add remote host to known_hosts | `ssh-keyscan` against `REMOTE_HOST` — prevents interactive host verification |

#### Deploy phase (executed on production server via SSH)

| # | Step | What it does |
|---|---|---|
| 11 | Copy bundle to remote | SCP `.tar.gz` to `/tmp/` on production server, saves filename to `$GITHUB_ENV` |
| 12 | Extract & deploy bundle | SSH → extract bundle → run `deploy_complete_bundle.sh --install-wheel` |
| 13 | Rebuild frontend on remote | SSH → `rm -rf dist && npm run build` in `dashboard/frontend/` — required because UI is served as static files from port 8000 |
| 14 | Force reinstall wheel in venv | SSH → `pip install --no-deps --force-reinstall teamsight-*.whl` into `dashboard/backend/venv/` |
| 15 | Restart backend service | SSH → `./manage.sh restart backend` |

#### Post-deploy

| # | Step | What it does |
|---|---|---|
| 16 | Verify deployment | Wait 8s → `manage.sh status` + curl `/api/config` to print deployed version |
| 17 | Clean up remote bundle | Always runs — deletes `/tmp/<bundle>.tar.gz` and `/tmp/ts_deploy/` from server |

---

## Infrastructure

```
AWS Cloud
├── EC2 — GitHub Enterprise Server (github01.hclpnp.com)
│           Hosts git repos, Actions UI, secrets store
│
├── EC2 — Self-hosted Runner (ubuntu-runner1)
│           Polls GHE for queued jobs, runs CI/CD workflows
│
└── EC2 — Production Server (REMOTE_HOST)
            Runs the FastAPI backend + serves React frontend
            Deployment path: /opt/teamsight/teamsight
```

## Key Notes

- **Frontend is not built locally for deployment** — `npm run build` runs on the production server after each deploy because the UI is served as static files from FastAPI on port 8000 (Vite dev server port 5173 is not open on the remote).
- **Wheel is force-reinstalled** on every deploy regardless of version number to ensure the backend venv always has the latest code.
- **Runtime data is never overwritten** by default — `config/`, `output/`, `data/`, `users.json` on the production server are preserved across deploys.
- **CD never triggers automatically** — must be manually initiated to prevent accidental production deployments.
