#!/usr/bin/env bash
set -euo pipefail

# Parameterized Chrome launcher for JSReverser / CDP based reverse workflows.
# All knobs can be overridden by environment variables.

CHROME_PATH="${CHROME_PATH:-/Applications/Google Chrome.app/Contents/MacOS/Google Chrome}"
CHROME_APP_NAME="${CHROME_APP_NAME:-Google Chrome}"
DEBUG_PORT="${DEBUG_PORT:-9222}"
DEBUG_ADDRESS="${DEBUG_ADDRESS:-127.0.0.1}"
USER_DATA_DIR="${USER_DATA_DIR:-${HOME}/.codex/browser-profiles/chrome-jsreverser}"
STATE_DIR="${STATE_DIR:-${HOME}/.codex/run/reverse-deepagent}"
START_URL="${START_URL:-about:blank}"
WAIT_SECONDS="${WAIT_SECONDS:-10}"
EXTRA_CHROME_ARGS="${EXTRA_CHROME_ARGS:-}"
PID_FILE="${PID_FILE:-$STATE_DIR/chrome-$DEBUG_PORT.pid}"
OWNERSHIP_FILE="${OWNERSHIP_FILE:-$STATE_DIR/chrome-$DEBUG_PORT.managed}"

listener_pids() {
  lsof -tiTCP:"$DEBUG_PORT" -sTCP:LISTEN 2>/dev/null || true
}

is_managed_pid() {
  local pid="$1"
  local cmd
  cmd="$(ps -p "$pid" -o command= 2>/dev/null || true)"
  [[ -n "$cmd" && "$cmd" == *"--remote-debugging-port=$DEBUG_PORT"* && "$cmd" == *"--user-data-dir=$USER_DATA_DIR"* ]]
}

write_state() {
  local pid="$1"
  mkdir -p "$STATE_DIR"
  printf '%s\n' "$pid" > "$PID_FILE"
  cat > "$OWNERSHIP_FILE" <<STATE
managed=true
pid=$pid
debug_port=$DEBUG_PORT
debug_address=$DEBUG_ADDRESS
user_data_dir=$USER_DATA_DIR
chrome_path=$CHROME_PATH
started_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)
STATE
}

if [[ ! -x "$CHROME_PATH" ]]; then
  echo "Chrome not found or not executable: $CHROME_PATH" >&2
  exit 1
fi

mkdir -p "$STATE_DIR" "$USER_DATA_DIR"

existing_pids="$(listener_pids)"
if [[ -n "$existing_pids" ]]; then
  while IFS= read -r pid; do
    [[ -z "$pid" ]] && continue
    if is_managed_pid "$pid"; then
      write_state "$pid"
      echo "Managed Chrome already listening on $DEBUG_ADDRESS:$DEBUG_PORT"
      echo "PID file: $PID_FILE"
      exit 0
    fi
  done <<< "$existing_pids"

  rm -f "$PID_FILE" "$OWNERSHIP_FILE"
  echo "Port $DEBUG_PORT is already used by an unmanaged listener; reusing it without taking ownership"
  exit 0
fi

extra_args=()
if [[ -n "$EXTRA_CHROME_ARGS" ]]; then
  read -r -a extra_args <<< "$EXTRA_CHROME_ARGS"
fi

open_args=(
  --remote-debugging-port="$DEBUG_PORT"
  --remote-debugging-address="$DEBUG_ADDRESS"
  --user-data-dir="$USER_DATA_DIR"
  --no-first-run
  --no-default-browser-check
)
if [[ "${#extra_args[@]}" -gt 0 ]]; then
  open_args+=("${extra_args[@]}")
fi
open_args+=("$START_URL")

open -na "$CHROME_APP_NAME" --args "${open_args[@]}"
attempts=$(( WAIT_SECONDS * 2 ))
if [[ "$attempts" -lt 1 ]]; then
  attempts=1
fi

for _ in $(seq 1 "$attempts"); do
  current_pids="$(listener_pids)"
  if [[ -n "$current_pids" ]]; then
    while IFS= read -r pid; do
      [[ -z "$pid" ]] && continue
      if is_managed_pid "$pid"; then
        write_state "$pid"
        echo "Started managed Chrome with remote debugging on $DEBUG_ADDRESS:$DEBUG_PORT"
        echo "User data dir: $USER_DATA_DIR"
        echo "PID file: $PID_FILE"
        exit 0
      fi
    done <<< "$current_pids"
  fi
  sleep 0.5
done

rm -f "$PID_FILE" "$OWNERSHIP_FILE"
echo "Chrome did not expose a managed listener on $DEBUG_ADDRESS:$DEBUG_PORT in time" >&2
exit 1
