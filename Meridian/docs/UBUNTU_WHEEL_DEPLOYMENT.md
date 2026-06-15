# TeamSight Wheel Deployment (Option A)

This guide covers TeamSight wheel packaging and the recommended Ubuntu deployment bundle that includes runtime files and dashboard source.

Wheel-provided CLI commands:
- `teamsight-kpi`
- `teamsight-jira-fetch`
- `teamsight-github-fetch`

Validated remote deployment path used in production troubleshooting:
- `/opt/teamsight/teamsight`

## 1) Build wheel from source

From the TeamSight project root:

Recommended (prompts for version):

```bash
./scripts/build_wheel.sh
```

Direct version (non-interactive):

```bash
./scripts/build_wheel.sh 0.1.3
```

Manual alternative:

```bash
# Use your preferred Python 3.10+ environment
python -m pip install --upgrade pip build
python -m build --wheel
```

Wheel output:
- `dist/teamsight-<version>-py3-none-any.whl`

## 1.5) Create one complete bundle (recommended)

Create a single archive containing runtime data + dashboard source + wheel + deploy helper:

```bash
./scripts/package_complete_bundle.sh --target-folder /opt/teamsight/teamsight
```

This creates:
- `dist/teamsight-complete-<timestamp>.tar.gz`

Bundle includes:
- `config/`, `data/`, `output/`
- `dashboard/` (frontend + backend source, `manage.sh`, `setup.sh`)
- `dist/teamsight-<version>-py3-none-any.whl`
- `scripts/deploy_complete_bundle.sh`
- `teamsight_env.sh`, `DEPLOY_INSTRUCTIONS.txt`, `BUNDLE_MANIFEST.txt`

## 2) Deploy complete bundle on Ubuntu

Install OS prerequisites:

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip nodejs npm
```

Copy and extract the bundle:

```bash
scp dist/teamsight-complete-<timestamp>.tar.gz root@<ubuntu-host>:/tmp/
sudo mkdir -p /opt/teamsight/teamsight
sudo tar -xzf /tmp/teamsight-complete-<timestamp>.tar.gz -C /opt/teamsight/teamsight
```

Run the deploy helper (recommended):

```bash
chmod +x /opt/teamsight/teamsight/scripts/deploy_complete_bundle.sh
/opt/teamsight/teamsight/scripts/deploy_complete_bundle.sh \
  --bundle /tmp/teamsight-complete-<timestamp>.tar.gz \
  --target-folder /opt/teamsight/teamsight \
  --run-setup \
  --start-services \
  --sudo \
  --no-prompt
```

What this does:
- extracts/refreshes files under the target folder
- configures `TEAMSIGHT_HOME` through `teamsight_env.sh`
- creates/updates backend venv with Python 3.10+
- installs backend requirements
- installs the bundled wheel into `dashboard/backend/venv`
- optionally runs setup and starts services

## 3) Build frontend and serve UI via backend (recommended for remote access)

When port `5173` is not reachable remotely, use this flow. It serves the built React UI directly from FastAPI on port `8000`.

```bash
cd /opt/teamsight/teamsight/dashboard/frontend
npm run build

cd /opt/teamsight/teamsight
./dashboard/manage.sh restart backend

# Optional: stop Vite dev server if not needed
./dashboard/manage.sh stop frontend
```

Open the UI at:
- `http://<ubuntu-host>:8000`

Quick verification:

```bash
curl -s http://127.0.0.1:8000 | head -5
```

Expected output starts with HTML (for example `<!doctype html>`), not JSON.

## 4) Manual alternative (without deploy helper)

```bash
source /opt/teamsight/teamsight/teamsight_env.sh
cd /opt/teamsight/teamsight/dashboard
chmod +x setup.sh manage.sh
./setup.sh
/opt/teamsight/teamsight/dashboard/backend/venv/bin/python -m pip install --upgrade /opt/teamsight/teamsight/dist/teamsight-<version>-py3-none-any.whl

# For local dev mode (frontend on 5173)
./manage.sh start all
./manage.sh status
```

## 5) Verify CLI commands

```bash
source /opt/teamsight/teamsight/teamsight_env.sh
teamsight-kpi --list
teamsight-jira-fetch --help
teamsight-github-fetch checkpoint
```

## 6) Package and deploy runtime files only (config / data / output)

Use this when you want to transfer or refresh the runtime data — `config/`, `data/`, `output/` — without re-deploying the full dashboard bundle.

### Create runtime-only archive (on source machine)

```bash
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
tar -czf dist/teamsight-runtime-${TIMESTAMP}.tar.gz config data output
```

### Copy to Ubuntu target

```bash
scp dist/teamsight-runtime-${TIMESTAMP}.tar.gz root@<ubuntu-host>:/tmp/
```

### Extract on Ubuntu (merges into existing target folder)

```bash
sudo tar -xzf /tmp/teamsight-runtime-${TIMESTAMP}.tar.gz -C /opt/teamsight/teamsight
```

This overwrites only `config/`, `data/`, and `output/` — it does not touch `dashboard/` or the backend venv.

### Restart backend to pick up config changes

If you updated `config/Resources.csv`, `config/Roles.csv`, or KPI scripts:

```bash
cd /opt/teamsight/teamsight/dashboard
./manage.sh restart backend
```

### Verify `TEAMSIGHT_HOME`

```bash
source /opt/teamsight/teamsight/teamsight_env.sh
teamsight-kpi --list
```

---

## 7) Upgrade wheel later

If you ship a newer wheel separately:

```bash
/opt/teamsight/teamsight/dashboard/backend/venv/bin/python -m pip install --upgrade /path/to/teamsight-<new-version>-py3-none-any.whl
cd /opt/teamsight/teamsight/dashboard
./manage.sh restart backend
```

## 8) Optional: CLI-only install (no dashboard)

```bash
cd /opt/teamsight
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install /path/to/teamsight-<version>-py3-none-any.whl
export TEAMSIGHT_HOME=/opt/teamsight
```

## 9) Troubleshooting

### "Permission denied" under `/root/...`

Do not run TeamSight from `/root/...` when using a non-root user. Deploy under `/opt/teamsight/teamsight` (or another non-root path) and ensure ownership.

### Backend works on `:8000`, UI not reachable on `:5173`

Use the recommended remote flow in Section 3:
- `npm run build`
- `./dashboard/manage.sh restart backend`
- open `http://<ubuntu-host>:8000`

### JIRA fetch needs more than default timeout

Default JIRA fetch timeout is `360` minutes. Override it before starting backend:

```bash
export TEAMSIGHT_JIRA_FETCH_TIMEOUT_MINUTES=720
cd /opt/teamsight/teamsight
./dashboard/manage.sh restart backend
```

### "Installed wheel but files are not in /opt/teamsight/teamsight"

Expected behavior. Wheel files install into Python environment `site-packages`, not into runtime folder directly.

Check install location:

```bash
which teamsight-kpi
python3 -c "import KppEvaluator, github_fetch, jira_fetch; print(KppEvaluator.__file__); print(github_fetch.__file__); print(jira_fetch.__file__)"
```

### Backend fails with `ModuleNotFoundError: KppEvaluator`

Install the wheel into the backend venv used by `manage.sh`:

```bash
/opt/teamsight/teamsight/dashboard/backend/venv/bin/python -m pip install --upgrade /opt/teamsight/teamsight/dist/teamsight-<version>-py3-none-any.whl
```

Then restart backend:

```bash
cd /opt/teamsight/teamsight/dashboard
./manage.sh restart backend
```

## Notes

- Primary deployment workflow is the single complete bundle (`package_complete_bundle.sh` + `deploy_complete_bundle.sh`).
- For remote access, serving built frontend through backend `:8000` is the most reliable path.
- Path resolution order in CLIs:
  1. `--project-root` (KPI CLI only)
  2. `TEAMSIGHT_HOME`
  3. current working directory (if it has `config/`)
  4. source-root fallback
