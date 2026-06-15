#!/usr/bin/env bash
set -euo pipefail

print_usage() {
  cat <<'EOF'
Usage: ./scripts/deploy_complete_bundle.sh --bundle /path/to/teamsight-complete-<timestamp>.tar.gz [options]

Deploy ONE TeamSight complete bundle on Ubuntu.
Bundle must include config/, data/, output/, dashboard/, and dist/teamsight-*.whl.

Options:
  --bundle PATH         Path to complete bundle tar.gz (required unless prompted)
  --target-folder PATH  Deployment target folder (default: /opt/teamsight)
  --shell-rc PATH       Shell rc file to update (default: ~/.bashrc)
  --no-shell-rc         Do not modify shell rc file
  --run-setup           Run dashboard/setup.sh after extraction
  --start-services      Run dashboard/manage.sh start all after extraction
  --install-wheel       Force wheel install into backend venv (default: true)
  --no-install-wheel    Skip wheel install
  --sudo                Always use sudo for filesystem operations
  --no-sudo             Never use sudo
  --no-prompt           Non-interactive mode
  -h, --help            Show this help
EOF
}

BUNDLE_PATH=""
TARGET_FOLDER="/opt/teamsight"
SHELL_RC="${HOME}/.bashrc"
UPDATE_SHELL_RC=true
NO_PROMPT=false
SUDO_MODE="auto"  # auto | always | never
RUN_SETUP=false
START_SERVICES=false
INSTALL_WHEEL=true

while [[ $# -gt 0 ]]; do
  case "$1" in
    --bundle)
      BUNDLE_PATH="${2:-}"
      shift 2
      ;;
    --target-folder)
      TARGET_FOLDER="${2:-}"
      shift 2
      ;;
    --shell-rc)
      SHELL_RC="${2:-}"
      shift 2
      ;;
    --no-shell-rc)
      UPDATE_SHELL_RC=false
      shift
      ;;
    --run-setup)
      RUN_SETUP=true
      shift
      ;;
    --start-services)
      START_SERVICES=true
      shift
      ;;
    --install-wheel)
      INSTALL_WHEEL=true
      shift
      ;;
    --no-install-wheel)
      INSTALL_WHEEL=false
      shift
      ;;
    --sudo)
      SUDO_MODE="always"
      shift
      ;;
    --no-sudo)
      SUDO_MODE="never"
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

if [[ "${START_SERVICES}" == true ]]; then
  RUN_SETUP=true
fi

if [[ -z "${BUNDLE_PATH}" ]]; then
  DEFAULT_BUNDLE="$(ls -1t ./teamsight-complete-*.tar.gz /tmp/teamsight-complete-*.tar.gz 2>/dev/null | head -n 1 || true)"

  if [[ "${NO_PROMPT}" == false ]]; then
    if [[ -n "${DEFAULT_BUNDLE}" ]]; then
      read -r -p "Bundle path (default: ${DEFAULT_BUNDLE}): " BUNDLE_PATH
      BUNDLE_PATH="${BUNDLE_PATH:-${DEFAULT_BUNDLE}}"
    else
      read -r -p "Bundle path: " BUNDLE_PATH
    fi
  elif [[ -n "${DEFAULT_BUNDLE}" ]]; then
    BUNDLE_PATH="${DEFAULT_BUNDLE}"
  fi
fi

if [[ -z "${BUNDLE_PATH}" ]]; then
  echo "Error: --bundle is required."
  exit 1
fi

if [[ ! -f "${BUNDLE_PATH}" ]]; then
  echo "Error: bundle not found: ${BUNDLE_PATH}"
  exit 1
fi

if [[ ! "${BUNDLE_PATH}" =~ \.tar\.gz$ ]]; then
  echo "Error: bundle must be a .tar.gz file"
  exit 1
fi

resolve_abs_path() {
  local input_path="$1"

  if command -v python3 >/dev/null 2>&1; then
    INPUT_PATH="${input_path}" python3 - <<'PY'
import os
path_value = os.environ['INPUT_PATH']
print(os.path.abspath(os.path.expanduser(path_value)))
PY
    return
  fi

  if [[ "${input_path}" == ~* ]]; then
    input_path="${HOME}${input_path:1}"
  fi

  if [[ "${input_path}" = /* ]]; then
    printf '%s\n' "${input_path}"
    return
  fi

  printf '%s/%s\n' "$(pwd)" "${input_path}"
}

resolve_sudo() {
  local mode="$1"
  local target="$2"

  if [[ "${mode}" == "never" ]]; then
    echo ""
    return
  fi

  if [[ "${mode}" == "always" ]]; then
    if [[ "$(id -u)" -eq 0 ]]; then
      echo ""
      return
    fi
    if command -v sudo >/dev/null 2>&1; then
      echo "sudo"
      return
    fi
    echo "Error: --sudo requested but sudo command is unavailable." >&2
    exit 1
  fi

  if [[ "$(id -u)" -eq 0 ]]; then
    echo ""
    return
  fi

  local parent
  parent="$(dirname "${target}")"

  if { [[ -d "${target}" ]] && [[ -w "${target}" ]]; } || { [[ ! -d "${target}" ]] && [[ -d "${parent}" ]] && [[ -w "${parent}" ]]; }; then
    echo ""
    return
  fi

  if command -v sudo >/dev/null 2>&1; then
    echo "sudo"
    return
  fi

  echo "Error: target '${target}' requires elevated permissions, but sudo is unavailable." >&2
  exit 1
}

python_supports_teamsight() {
  local py_exec="$1"
  "${py_exec}" - <<'PY' >/dev/null 2>&1
import sys
raise SystemExit(0 if sys.version_info >= (3, 10) else 1)
PY
}

select_backend_python() {
  local candidate
  for candidate in python3.12 python3.11 python3.10 python3 python; do
    if command -v "${candidate}" >/dev/null 2>&1; then
      if python_supports_teamsight "${candidate}"; then
        echo "${candidate}"
        return 0
      fi
    fi
  done

  return 1
}

run_cmd() {
  if [[ -n "${SUDO_CMD}" ]]; then
    ${SUDO_CMD} "$@"
  else
    "$@"
  fi
}

TARGET_FOLDER="$(resolve_abs_path "${TARGET_FOLDER}")"
BUNDLE_PATH="$(resolve_abs_path "${BUNDLE_PATH}")"
SUDO_CMD="$(resolve_sudo "${SUDO_MODE}" "${TARGET_FOLDER}")"

ENV_FILE="${TARGET_FOLDER}/teamsight_env.sh"
DASHBOARD_DIR="${TARGET_FOLDER}/dashboard"
BACKEND_DIR="${DASHBOARD_DIR}/backend"
BACKEND_VENV_PYTHON="${BACKEND_DIR}/venv/bin/python"

echo "Deploying complete bundle: ${BUNDLE_PATH}"
echo "Target folder: ${TARGET_FOLDER}"
if [[ -n "${SUDO_CMD}" ]]; then
  echo "Using elevated operations via sudo"
fi

run_cmd mkdir -p "${TARGET_FOLDER}"
run_cmd tar -xzf "${BUNDLE_PATH}" -C "${TARGET_FOLDER}"

if [[ -n "${SUDO_CMD}" ]] && [[ "$(id -u)" -ne 0 ]]; then
  run_cmd chown -R "${USER}:${USER}" "${TARGET_FOLDER}" || true
fi

if [[ -f "${DASHBOARD_DIR}/manage.sh" ]]; then
  chmod +x "${DASHBOARD_DIR}/manage.sh"
fi
if [[ -f "${DASHBOARD_DIR}/setup.sh" ]]; then
  chmod +x "${DASHBOARD_DIR}/setup.sh"
fi
if [[ -f "${TARGET_FOLDER}/teamsight_env.sh" ]]; then
  chmod 0644 "${TARGET_FOLDER}/teamsight_env.sh"
fi

if [[ "${UPDATE_SHELL_RC}" == true ]]; then
  mkdir -p "$(dirname "${SHELL_RC}")"
  touch "${SHELL_RC}"
  SOURCE_LINE="source \"${ENV_FILE}\""
  if grep -Fqx "${SOURCE_LINE}" "${SHELL_RC}"; then
    echo "Shell profile already configured: ${SHELL_RC}"
  else
    echo "${SOURCE_LINE}" >> "${SHELL_RC}"
    echo "Added TEAMSIGHT_HOME source line to ${SHELL_RC}"
  fi
fi

if [[ "${RUN_SETUP}" == true ]]; then
  echo
  echo "Running dashboard setup..."
  (
    cd "${DASHBOARD_DIR}"
    ./setup.sh
  )
fi

install_wheel_into_backend() {
  local wheel_file
  local backend_python_cmd

  if [[ "${INSTALL_WHEEL}" == false ]]; then
    echo "Skipping wheel installation (--no-install-wheel)."
    return 0
  fi

  wheel_file="$(ls -1t "${TARGET_FOLDER}"/dist/teamsight-*.whl 2>/dev/null | head -n 1 || true)"
  if [[ -z "${wheel_file}" ]]; then
    echo "Error: No TeamSight wheel found under ${TARGET_FOLDER}/dist"
    exit 1
  fi

  backend_python_cmd="$(select_backend_python || true)"
  if [[ -z "${backend_python_cmd}" ]]; then
    echo "Error: Python 3.10+ is required to create/update backend venv."
    exit 1
  fi

  if [[ ! -x "${BACKEND_VENV_PYTHON}" ]]; then
    echo "Backend venv not found. Creating with ${backend_python_cmd} ..."
    (
      cd "${BACKEND_DIR}"
      "${backend_python_cmd}" -m venv venv
    )
  elif ! python_supports_teamsight "${BACKEND_VENV_PYTHON}"; then
    echo "Backend venv Python is < 3.10. Recreating with ${backend_python_cmd} ..."
    rm -rf "${BACKEND_DIR}/venv"
    (
      cd "${BACKEND_DIR}"
      "${backend_python_cmd}" -m venv venv
    )
  fi

  echo
  echo "Installing backend requirements + TeamSight wheel..."
  "${BACKEND_VENV_PYTHON}" -m pip install --upgrade pip

  if [[ -f "${BACKEND_DIR}/requirements.txt" ]]; then
    "${BACKEND_VENV_PYTHON}" -m pip install -r "${BACKEND_DIR}/requirements.txt"
  fi

  "${BACKEND_VENV_PYTHON}" -m pip install --upgrade "${wheel_file}"

  if ! "${BACKEND_VENV_PYTHON}" -c "import KppEvaluator" >/dev/null 2>&1; then
    echo "Error: KppEvaluator import failed after wheel install."
    exit 1
  fi

  echo "Wheel installed in backend venv: ${wheel_file}"
}

install_wheel_into_backend

if [[ "${START_SERVICES}" == true ]]; then
  echo
  echo "Starting dashboard services..."
  (
    cd "${DASHBOARD_DIR}"
    ./manage.sh start all
  )
fi

echo
echo "✅ Complete bundle deployed"
echo "   Target root: ${TARGET_FOLDER}"
echo "   Dashboard: ${DASHBOARD_DIR}"
echo "   TEAMSIGHT_HOME file: ${ENV_FILE}"
if [[ "${UPDATE_SHELL_RC}" == true ]]; then
  echo "   Shell profile updated: ${SHELL_RC}"
fi
echo
echo "Next steps:"
echo "  source \"${ENV_FILE}\""
echo "  cd \"${DASHBOARD_DIR}\""
if [[ "${RUN_SETUP}" == false ]]; then
  echo "  ./setup.sh"
fi
if [[ "${START_SERVICES}" == false ]]; then
  echo "  ./manage.sh start all"
fi
echo "  ./manage.sh status"
