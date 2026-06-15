# TeamSight Deployment Steps

## Overview

This document describes how to build a new code-only package (no runtime data) and deploy it to the remote server.

**Remote server:** `root@10.222.2.217`
**Remote target folder:** `/opt/teamsight/teamsight`

---

## Step 1 — Build the Wheel

Run the wheel build script with the desired version number:

```bash
echo "y" | ./scripts/build_wheel.sh <version>
```

**Example:**
```bash
echo "y" | ./scripts/build_wheel.sh 1.2.0
```

The built wheel will be placed in `dist/`:
```
dist/teamsight-<version>-py3-none-any.whl
```

> The `echo "y"` automatically confirms if the version is unchanged. If bumping the version, it will update `setup.py` automatically.

---

## Step 2 — Package the Bundle

### Default — Code-only bundle

This is now the default and should be used for normal deployments so remote collected data is not overwritten.

```bash
./scripts/package_complete_bundle.sh \
  --no-prompt \
  --target-folder /opt/teamsight/teamsight
```

### Optional — Full bundle

Use this only when you explicitly want to push runtime/config data after review and confirmation.

```bash
./scripts/package_complete_bundle.sh \
  --include-runtime-data \
  --no-prompt \
  --target-folder /opt/teamsight/teamsight
```

The bundle will be created in `dist/`:
```
dist/teamsight-complete-<timestamp>.tar.gz
```

> Any config file should be copied individually only after explicit confirmation.

---

## Step 3 — Copy Bundle to Remote Server

Transfer the bundle to the remote server's `/tmp/` directory:

```bash
scp dist/teamsight-complete-<timestamp>.tar.gz root@10.222.2.217:/tmp/
```

**Example:**
```bash
scp dist/teamsight-complete-20260318_165401.tar.gz root@10.222.2.217:/tmp/
```

---

## Step 4 — Deploy on Remote Server

SSH into the remote, extract, and run the deploy script:

```bash
ssh root@10.222.2.217 "
  mkdir -p /tmp/ts_deploy && \
  tar -xzf /tmp/teamsight-complete-<timestamp>.tar.gz -C /tmp/ts_deploy && \
  chmod +x /tmp/ts_deploy/scripts/deploy_complete_bundle.sh && \
  /tmp/ts_deploy/scripts/deploy_complete_bundle.sh \
    --bundle /tmp/teamsight-complete-<timestamp>.tar.gz \
    --target-folder /opt/teamsight/teamsight \
    --no-prompt \
    --install-wheel \
    --start-services
"
```

The deploy script will:
1. Extract the bundle to the target folder
2. Upgrade the TeamSight wheel in the backend venv
3. Start services if not already running

> **Important:** `--start-services` only starts services that are not running. If services were already running at deploy time, you must explicitly restart them to serve the new code (see Step 5).

---

## Step 5 — Rebuild the Frontend on Remote

> **Important:** Port 5173 is not open on the remote server. The UI is served as static files from port 8000 via FastAPI. A fresh `npm run build` must be run on the remote after every frontend code deploy to regenerate the `dist/` folder.

```bash
ssh root@10.222.2.217 "cd /opt/teamsight/teamsight/dashboard/frontend && npm run build"
```

---

## Step 6 — Restart Backend on Remote

Restart the backend so FastAPI remounts the newly built `dist/` folder:

```bash
ssh root@10.222.2.217 "cd /opt/teamsight/teamsight/dashboard && ./manage.sh restart backend"
```

> Only the backend needs restarting after a frontend rebuild. The Vite dev server (port 5173) is not used on remote.

---

## Step 7 — Verify

Check that the backend is up and the UI is accessible:

```bash
ssh root@10.222.2.217 "cd /opt/teamsight/teamsight/dashboard && ./manage.sh status"
```

Then open **`http://10.222.2.217:8000/`** in your browser.

## Step 8 — Security Scan Scheduler / KPI Verification

This release sets the default **Security Scan Report Fetch** schedule to **4:30 AM local time** and keeps **All KPI Computation** at **5:00 AM local time**.

It also adds an automatic follow-up refresh of scan-based KPIs:
- `k301`
- `k302`
- `k303`
- `k304`
- `k305`
- `k306`
- `k307`

Optional manual verification after deploy:

```bash
# Trigger scan download job
ssh root@10.222.2.217 "curl -X POST http://127.0.0.1:8000/api/jobs/security_scan_fetch/trigger"

# Or manually recompute the new scan KPIs on remote
ssh root@10.222.2.217 "cd /opt/teamsight/teamsight && .venv/bin/python src/KppEvaluator.py --kpis k301 k302 k303 k304 k305 k306 k307"
```

Expected output:
```
═══════════════════════════════════════
  Service Status
═══════════════════════════════════════

Backend:
✓ Running (PID: XXXXX)
✓ Responding on http://127.0.0.1:8000

Frontend:
✓ Running (PID: XXXXX)
✓ Responding on http://localhost:5173
```

---

## Quick Reference (Copy-Paste)

Replace `<version>` and `<timestamp>` with actual values:

```bash
# 1. Build wheel
echo "y" | ./scripts/build_wheel.sh <version>

# 2. Package bundle (default safe mode: no runtime data)
./scripts/package_complete_bundle.sh --no-prompt --target-folder /opt/teamsight/teamsight

# 3. Get the bundle filename
BUNDLE=$(ls -1t dist/teamsight-complete-*.tar.gz | head -1)
echo "Bundle: $BUNDLE"

# 4. SCP to remote
scp "$BUNDLE" root@10.222.2.217:/tmp/

# 5. Deploy on remote
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

# 6. Rebuild frontend on remote (required — UI is served as static files from port 8000)
ssh root@10.222.2.217 "cd /opt/teamsight/teamsight/dashboard/frontend && npm run build"

# 7. Restart backend so FastAPI remounts the new dist/
ssh root@10.222.2.217 "cd /opt/teamsight/teamsight/dashboard && ./manage.sh restart backend"

# 8. Verify — UI available at http://10.222.2.217:8000/
ssh root@10.222.2.217 "cd /opt/teamsight/teamsight/dashboard && ./manage.sh status"
```

---

## Notes

- **UI is served from port 8000**, not 5173. Port 5173 (Vite dev server) is not open on the remote. FastAPI mounts `frontend/dist/` as static files and serves the React app at `http://10.222.2.217:8000/`.
- **Frontend must be rebuilt on remote** (`npm run build`) after every frontend code deploy. Without this, the browser will serve the old compiled assets.
- **Backend restart is required** after a rebuild so FastAPI remounts the updated `dist/` folder.
- **Code-only deploys** (default): Safe to run anytime — do not overwrite live CSV data, `users.json`, scheduler state, or job output files on the remote.
- **Full deploys** (`--include-runtime-data`): Overwrite `config/`, `data/`, and `output/` on the remote. Use only when intentionally pushing runtime/config data.
- **Config files**: Copy individually only after validating the remote state and confirming the change.
- **Wheel version** should be bumped for each release to make rollbacks easier.
- **SSH key** must be configured for passwordless access to `root@10.222.2.217`.
