#!/usr/bin/env bash
set -euo pipefail

DEBUG_PORT="${DEBUG_PORT:-9222}"
USER_DATA_DIR="${USER_DATA_DIR:-${HOME}/.codex/browser-profiles/chrome-jsreverser}"
STATE_DIR="${STATE_DIR:-${HOME}/.codex/run/reverse-deepagent}"
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

if [[ ! -f "$PID_FILE" ]]; then
  if [[ -n "$(listener_pids)" ]]; then
    echo "Port $DEBUG_PORT is in use by an unmanaged listener; leaving it untouched"
    exit 0
  fi
  echo "No managed Chrome PID file found for port $DEBUG_PORT"
  exit 0
fi

pid="$(tr -d '[:space:]' < "$PID_FILE")"
if [[ -z "$pid" ]]; then
  rm -f "$PID_FILE" "$OWNERSHIP_FILE"
  echo "Managed Chrome PID file was empty; cleaned stale state"
  exit 0
fi

if ! is_managed_pid "$pid"; then
  rm -f "$PID_FILE" "$OWNERSHIP_FILE"
  echo "Managed Chrome PID file was stale or no longer points to the expected process; cleaned stale state"
  exit 0
fi

kill "$pid" 2>/dev/null || true

for _ in $(seq 1 10); do
  if ! ps -p "$pid" >/dev/null 2>&1 && [[ -z "$(listener_pids)" ]]; then
    rm -f "$PID_FILE" "$OWNERSHIP_FILE"
    echo "Stopped managed Chrome remote debugging listener on port $DEBUG_PORT"
    exit 0
  fi
  sleep 0.5
done

kill -TERM "$pid" 2>/dev/null || true
sleep 1
rm -f "$PID_FILE" "$OWNERSHIP_FILE"

echo "Stopped managed Chrome remote debugging listener on port $DEBUG_PORT"
