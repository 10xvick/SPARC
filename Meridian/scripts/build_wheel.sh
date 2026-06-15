#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
SETUP_FILE="${ROOT_DIR}/setup.py"

if [[ ! -f "${SETUP_FILE}" ]]; then
  echo "Error: setup.py not found at ${SETUP_FILE}"
  exit 1
fi

if [[ -x "${ROOT_DIR}/.venv/bin/python" ]]; then
  PYTHON_BIN="${ROOT_DIR}/.venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="$(command -v python3)"
elif command -v python >/dev/null 2>&1; then
  PYTHON_BIN="$(command -v python)"
else
  echo "Error: Python interpreter not found."
  exit 1
fi

CURRENT_VERSION="$("${PYTHON_BIN}" - <<'PY'
from pathlib import Path
import re
import sys

setup_text = Path('setup.py').read_text(encoding='utf-8')
match = re.search(r"^\s*version\s*=\s*['\"]([^'\"]+)['\"]\s*,\s*$", setup_text, re.MULTILINE)
if not match:
    print('UNKNOWN')
    sys.exit(0)
print(match.group(1))
PY
)"

NEW_VERSION="${1:-}"
if [[ -z "${NEW_VERSION}" ]]; then
  read -r -p "Enter new wheel version (current: ${CURRENT_VERSION}): " NEW_VERSION
fi

if [[ -z "${NEW_VERSION}" ]]; then
  echo "Error: version is required."
  exit 1
fi

if [[ ! "${NEW_VERSION}" =~ ^[0-9]+(\.[0-9]+)*([a-zA-Z0-9][a-zA-Z0-9._-]*)?$ ]]; then
  echo "Error: invalid version '${NEW_VERSION}'. Use formats like 0.1.2, 1.0.0rc1, 2.3.4.post1"
  exit 1
fi

if [[ "${NEW_VERSION}" == "${CURRENT_VERSION}" ]]; then
  read -r -p "Version is unchanged (${CURRENT_VERSION}). Build anyway? [y/N]: " CONFIRM
  if [[ ! "${CONFIRM}" =~ ^[Yy]$ ]]; then
    echo "Aborted."
    exit 1
  fi
fi

export TEAMSIGHT_SETUP_FILE="${SETUP_FILE}"
export TEAMSIGHT_NEW_VERSION="${NEW_VERSION}"
export TEAMSIGHT_PYTHON_BIN="${PYTHON_BIN}"

"${PYTHON_BIN}" - <<'PY'
import os
import re
import sys
from pathlib import Path

setup_file = Path(os.environ['TEAMSIGHT_SETUP_FILE'])
new_version = os.environ['TEAMSIGHT_NEW_VERSION']

text = setup_file.read_text(encoding='utf-8')
pattern = r"(?m)^(\s*version\s*=\s*['\"])([^'\"]+)(['\"]\s*,\s*)$"
match = re.search(pattern, text)
if not match:
    print(f"Error: Could not find version field in {setup_file}")
    sys.exit(1)

old_version = match.group(2)
updated_text = text[:match.start(2)] + new_version + text[match.end(2):]
setup_file.write_text(updated_text, encoding='utf-8')
print(f"Updated setup.py version: {old_version} -> {new_version}")
PY

cd "${ROOT_DIR}"

echo "Installing/upgrading build package..."
"${PYTHON_BIN}" -m pip install --upgrade build

echo "Cleaning old artifacts..."
rm -rf build dist src/teamsight.egg-info

echo "Building wheel..."
"${PYTHON_BIN}" -m build --wheel

LATEST_WHEEL="$(ls -1t dist/*.whl | head -n 1)"

echo
echo "✅ Wheel created successfully"
echo "   ${LATEST_WHEEL}"
