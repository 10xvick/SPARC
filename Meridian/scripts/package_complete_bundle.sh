#!/usr/bin/env bash
set -euo pipefail

print_usage() {
  cat <<'EOF'
Usage: ./scripts/package_complete_bundle.sh [options]

Create ONE deployment bundle containing:
- dashboard/ (frontend + backend source)
- latest TeamSight wheel (dist/teamsight-*.whl)
- scripts/deploy_complete_bundle.sh

By default, runtime data is EXCLUDED:
- config/
- data/
- output/

Options:
  --target-folder PATH         Target folder on Ubuntu (default: /opt/teamsight)
  --output-dir PATH            Bundle output directory (default: <repo>/dist)
  --bundle-name NAME           Bundle file prefix (default: teamsight-complete)
  --wheel PATH                 Explicit wheel path (default: latest dist/teamsight-*.whl)
  --include-node-modules       Include dashboard/frontend/node_modules (default: excluded)
  --include-backend-venv       Include dashboard/backend/venv (default: excluded)
  --include-runtime-data       Include config/, data/, output/ in the bundle
                               (use only when intentionally pushing runtime/config data)
  --no-runtime-data            Deprecated no-op; runtime data is already excluded by default
  --no-prompt                  Non-interactive mode
  -h, --help                   Show help
EOF
}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

TARGET_FOLDER=""
OUTPUT_DIR=""
BUNDLE_NAME="teamsight-complete"
WHEEL_PATH=""
NO_PROMPT=false
INCLUDE_NODE_MODULES=false
INCLUDE_BACKEND_VENV=false
INCLUDE_RUNTIME_DATA=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --target-folder)
      TARGET_FOLDER="${2:-}"
      shift 2
      ;;
    --output-dir)
      OUTPUT_DIR="${2:-}"
      shift 2
      ;;
    --bundle-name)
      BUNDLE_NAME="${2:-}"
      shift 2
      ;;
    --wheel)
      WHEEL_PATH="${2:-}"
      shift 2
      ;;
    --include-node-modules)
      INCLUDE_NODE_MODULES=true
      shift
      ;;
    --include-backend-venv)
      INCLUDE_BACKEND_VENV=true
      shift
      ;;
    --include-runtime-data)
      INCLUDE_RUNTIME_DATA=true
      shift
      ;;
    --no-runtime-data)
      INCLUDE_RUNTIME_DATA=false
      shift
      ;;
    --no-prompt)
      NO_PROMPT=true
      shift
      ;;
    -h|--help)
      print_usage
      exit 0
      ;;
    *)
      echo "Error: unknown option '$1'"
      print_usage
      exit 1
      ;;
  esac
done

if [[ -z "${TARGET_FOLDER}" ]]; then
  if [[ "${NO_PROMPT}" == false ]]; then
    read -r -p "Target folder on Ubuntu (default: /opt/teamsight): " TARGET_FOLDER
  fi
  TARGET_FOLDER="${TARGET_FOLDER:-/opt/teamsight}"
fi

if [[ -z "${OUTPUT_DIR}" ]]; then
  OUTPUT_DIR="${ROOT_DIR}/dist"
fi

for required_dir in config data output dashboard; do
  if [[ "${required_dir}" != "config" && "${required_dir}" != "data" && "${required_dir}" != "output" ]]; then
    if [[ ! -d "${ROOT_DIR}/${required_dir}" ]]; then
      echo "Error: required directory missing: ${ROOT_DIR}/${required_dir}"
      exit 1
    fi
  elif [[ "${INCLUDE_RUNTIME_DATA}" == true ]]; then
    if [[ ! -d "${ROOT_DIR}/${required_dir}" ]]; then
      echo "Error: required directory missing: ${ROOT_DIR}/${required_dir}"
      exit 1
    fi
  fi
done

if [[ ! -f "${ROOT_DIR}/scripts/deploy_complete_bundle.sh" ]]; then
  echo "Error: required script missing: ${ROOT_DIR}/scripts/deploy_complete_bundle.sh"
  exit 1
fi

if [[ -z "${WHEEL_PATH}" ]]; then
  WHEEL_PATH="$(ls -1t "${ROOT_DIR}"/dist/teamsight-*.whl 2>/dev/null | head -n 1 || true)"
fi

if [[ -z "${WHEEL_PATH}" ]]; then
  echo "Error: no TeamSight wheel found in ${ROOT_DIR}/dist"
  echo "Run ./scripts/build_wheel.sh first, or pass --wheel /path/to/teamsight-<version>.whl"
  exit 1
fi

if [[ ! -f "${WHEEL_PATH}" ]]; then
  echo "Error: wheel file not found: ${WHEEL_PATH}"
  exit 1
fi

mkdir -p "${OUTPUT_DIR}"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
ARCHIVE_PATH="${OUTPUT_DIR}/${BUNDLE_NAME}-${TIMESTAMP}.tar.gz"

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "${TMP_DIR}"' EXIT

if [[ "${INCLUDE_RUNTIME_DATA}" == true ]]; then
  cp -a "${ROOT_DIR}/config" "${TMP_DIR}/"
  cp -a "${ROOT_DIR}/data" "${TMP_DIR}/"
  cp -a "${ROOT_DIR}/output" "${TMP_DIR}/"
else
  echo "ℹ Skipping runtime data (config/, data/, output/) — default safe mode"
fi

if command -v rsync >/dev/null 2>&1; then
  EXCLUDES=(
    --exclude '.pids'
    --exclude 'logs'
    --exclude 'backend/.env'
    --exclude 'backend/backend.log'
    --exclude 'frontend/dist'
    --exclude '**/__pycache__'
    --exclude '*.pyc'
  )

  if [[ "${INCLUDE_NODE_MODULES}" == false ]]; then
    EXCLUDES+=(--exclude 'frontend/node_modules')
  fi

  if [[ "${INCLUDE_BACKEND_VENV}" == false ]]; then
    EXCLUDES+=(--exclude 'backend/venv')
  fi

  rsync -a "${EXCLUDES[@]}" "${ROOT_DIR}/dashboard/" "${TMP_DIR}/dashboard/"
else
  echo "Warning: rsync not found. Falling back to cp; this may be slower."
  cp -a "${ROOT_DIR}/dashboard" "${TMP_DIR}/dashboard"

  rm -rf "${TMP_DIR}/dashboard/.pids" "${TMP_DIR}/dashboard/logs" "${TMP_DIR}/dashboard/frontend/dist"
  rm -f "${TMP_DIR}/dashboard/backend/.env"
  rm -f "${TMP_DIR}/dashboard/backend/backend.log"

  if [[ "${INCLUDE_NODE_MODULES}" == false ]]; then
    rm -rf "${TMP_DIR}/dashboard/frontend/node_modules"
  fi

  if [[ "${INCLUDE_BACKEND_VENV}" == false ]]; then
    rm -rf "${TMP_DIR}/dashboard/backend/venv"
  fi

  find "${TMP_DIR}/dashboard" -type d -name '__pycache__' -prune -exec rm -rf {} +
  find "${TMP_DIR}/dashboard" -type f -name '*.pyc' -delete
fi

# Always include src/ — contains job scripts and KPI evaluators needed at runtime
if [[ -d "${ROOT_DIR}/src" ]]; then
  rsync -a \
    --exclude '__pycache__' \
    --exclude '*.pyc' \
    "${ROOT_DIR}/src/" "${TMP_DIR}/src/"
else
  echo "Warning: src/ directory not found at ${ROOT_DIR}/src — skipping"
fi

mkdir -p "${TMP_DIR}/dist"
cp -a "${WHEEL_PATH}" "${TMP_DIR}/dist/"
WHEEL_NAME="$(basename "${WHEEL_PATH}")"

mkdir -p "${TMP_DIR}/scripts"
cp -a "${ROOT_DIR}/scripts/deploy_complete_bundle.sh" "${TMP_DIR}/scripts/"

cat > "${TMP_DIR}/teamsight_env.sh" <<EOF
export TEAMSIGHT_HOME="${TARGET_FOLDER}"
export TEAMSIGHT_JIRA_FETCH_TIMEOUT_MINUTES="${TEAMSIGHT_JIRA_FETCH_TIMEOUT_MINUTES:-720}"
EOF

cat > "${TMP_DIR}/DEPLOY_INSTRUCTIONS.txt" <<EOF
TeamSight Complete Bundle Deployment
====================================

1) Copy one bundle to Ubuntu:
   scp $(basename "${ARCHIVE_PATH}") <user>@<ubuntu-host>:/tmp/

2) Extract on Ubuntu:
   sudo mkdir -p "${TARGET_FOLDER}"
   sudo tar -xzf "/tmp/$(basename "${ARCHIVE_PATH}")" -C "${TARGET_FOLDER}"

3) Run scripted deploy (recommended):
  chmod +x "${TARGET_FOLDER}/scripts/deploy_complete_bundle.sh"
  "${TARGET_FOLDER}/scripts/deploy_complete_bundle.sh" \
    --bundle "/tmp/$(basename "${ARCHIVE_PATH}")" \
    --target-folder "${TARGET_FOLDER}" \
    --run-setup --start-services --no-prompt

4) Manual alternative (if you do not use deploy script):
   source "${TARGET_FOLDER}/teamsight_env.sh"
   cd "${TARGET_FOLDER}/dashboard"
   chmod +x setup.sh manage.sh
   ./setup.sh
   "${TARGET_FOLDER}/dashboard/backend/venv/bin/python" -m pip install --upgrade "${TARGET_FOLDER}/dist/${WHEEL_NAME}"
   ./manage.sh start all
   ./manage.sh status

Note:
- This bundle excludes config/, data/, and output/ by default.
- Copy any config files separately only after validating them.
EOF

{
  echo "TeamSight Complete Bundle"
  echo "Generated at: $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
  echo "Source root: ${ROOT_DIR}"
  echo "Suggested target folder: ${TARGET_FOLDER}"
  echo "Included wheel: dist/${WHEEL_NAME}"
  echo "Included node_modules: ${INCLUDE_NODE_MODULES}"
  echo "Included backend venv: ${INCLUDE_BACKEND_VENV}"
  echo "Included runtime data (config/data/output): ${INCLUDE_RUNTIME_DATA}"
  echo
  echo "Included files:"
  find "${TMP_DIR}" -type f | sed "s|${TMP_DIR}/||" | sort
} > "${TMP_DIR}/BUNDLE_MANIFEST.txt"
BUNDLE_PARTS=(dashboard dist scripts teamsight_env.sh DEPLOY_INSTRUCTIONS.txt BUNDLE_MANIFEST.txt)
if [[ -d "${TMP_DIR}/src" ]]; then
  BUNDLE_PARTS=(src "${BUNDLE_PARTS[@]}")
fi
if [[ "${INCLUDE_RUNTIME_DATA}" == true ]]; then
  BUNDLE_PARTS=(config data output "${BUNDLE_PARTS[@]}")
fi
tar -czf "${ARCHIVE_PATH}" -C "${TMP_DIR}" "${BUNDLE_PARTS[@]}"

FILE_COUNT="$(find "${TMP_DIR}" -type f | wc -l | tr -d ' ')"
ARCHIVE_SIZE="$(du -h "${ARCHIVE_PATH}" | awk '{print $1}')"

echo
echo "✅ Complete bundle created"
echo "   Archive: ${ARCHIVE_PATH}"
echo "   Size: ${ARCHIVE_SIZE}"
echo "   Files included: ${FILE_COUNT}"
echo "   Wheel included: dist/${WHEEL_NAME}"
echo "   Target folder hint: ${TARGET_FOLDER}"
if [[ "${INCLUDE_RUNTIME_DATA}" == false ]]; then
  echo "   ✓ Runtime data excluded by default (config/, data/, output/ not bundled)"
fi
