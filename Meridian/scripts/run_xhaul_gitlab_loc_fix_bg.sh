#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON_BIN="$ROOT_DIR/.venv/bin/python"
SCRIPT_PATH="$ROOT_DIR/scripts/fix_xhaul_gitlab_loc_consistency.py"
LOG_DIR="$ROOT_DIR/output/data_quality"
PID_DIR="$ROOT_DIR/output/data_quality"
TS="$(date +%Y%m%d_%H%M%S)"
LOG_FILE="$LOG_DIR/xhaul_gitlab_loc_fix_${TS}.log"
PID_FILE="$PID_DIR/xhaul_gitlab_loc_fix.pid"

mkdir -p "$LOG_DIR" "$PID_DIR"

if [ ! -x "$PYTHON_BIN" ]; then
  echo "python_not_found=$PYTHON_BIN"
  exit 1
fi

if [ -f "$PID_FILE" ]; then
  OLD_PID="$(cat "$PID_FILE" 2>/dev/null || true)"
  if [ -n "${OLD_PID}" ] && kill -0 "$OLD_PID" 2>/dev/null; then
    echo "already_running_pid=$OLD_PID"
    echo "log_file=$LOG_FILE"
    exit 0
  fi
fi

nohup "$PYTHON_BIN" "$SCRIPT_PATH" --project-root "$ROOT_DIR" > "$LOG_FILE" 2>&1 &
NEW_PID=$!
echo "$NEW_PID" > "$PID_FILE"

echo "started_pid=$NEW_PID"
echo "pid_file=$PID_FILE"
echo "log_file=$LOG_FILE"
