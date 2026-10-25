#!/usr/bin/env bash

set -u

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
CORE_DIR="$SCRIPT_DIR/c3a-core"
UI_DIR="$CORE_DIR/c3a-core-ui"
API_DIR="$CORE_DIR/c3a-core-api"
AI_DIR="$CORE_DIR/c3a-core-ai"
OLLAMA_MODEL="llama3.1:8b-instruct-q4_K_M"

fail() {
  printf 'ERROR: %s\n' "$1" >&2
  exit 1
}

find_python() {
  if [[ -x "$CORE_DIR/.venv/bin/python" ]]; then
    printf '%s\n' "$CORE_DIR/.venv/bin/python"
  elif [[ -x "$1/.venv/bin/python" ]]; then
    printf '%s\n' "$1/.venv/bin/python"
  elif command -v python3 >/dev/null 2>&1; then
    command -v python3
  elif command -v python >/dev/null 2>&1; then
    command -v python
  else
    return 1
  fi
}

[[ -f "$UI_DIR/package.json" ]] || fail "UI entrypoint not found: $UI_DIR/package.json"
[[ -f "$API_DIR/main.py" ]] || fail "API entrypoint not found: $API_DIR/main.py"
[[ -f "$AI_DIR/main.py" ]] || fail "AI entrypoint not found: $AI_DIR/main.py"
command -v npm >/dev/null 2>&1 || fail "npm was not found on PATH. Install Node.js first."
OLLAMA_BIN="$(command -v ollama)" || fail "Ollama was not found on PATH. Install Ollama first."

API_PYTHON="$(find_python "$API_DIR")" || fail "Python 3 was not found. Create .venv here or install Python 3."
AI_PYTHON="$(find_python "$AI_DIR")" || fail "Python 3 was not found. Create .venv here or install Python 3."

if [[ "${1:-}" == "--check" ]]; then
  printf 'C3A startup preflight passed.\n'
  printf 'API Python: %s\n' "$API_PYTHON"
  printf 'AI Python:  %s\n' "$AI_PYTHON"
  printf 'npm:        %s\n' "$(command -v npm)"
  printf 'Ollama:     %s\n' "$OLLAMA_BIN"
  printf 'AI model:   %s\n' "$OLLAMA_MODEL"
  if "$OLLAMA_BIN" list >/dev/null 2>&1; then
    printf 'Ollama server: running\n'
    if "$OLLAMA_BIN" show "$OLLAMA_MODEL" >/dev/null 2>&1; then
      printf 'AI model status: installed\n'
    else
      printf 'AI model status: not installed; normal startup will pull it\n'
    fi
  else
    printf 'Ollama server: not running; normal startup will start it\n'
  fi
  exit 0
fi

PIDS=()

cleanup() {
  trap - EXIT INT TERM
  printf '\nStopping C3A services...\n'
  for pid in "${PIDS[@]}"; do
    kill "$pid" 2>/dev/null || true
  done
  for pid in "${PIDS[@]}"; do
    wait "$pid" 2>/dev/null || true
  done
}

trap cleanup EXIT INT TERM

if "$OLLAMA_BIN" list >/dev/null 2>&1; then
  printf 'Ollama server is already running.\n'
else
  printf 'Starting Ollama server...\n'
  "$OLLAMA_BIN" serve &
  PIDS+=("$!")

  OLLAMA_READY=false
  for _ in {1..30}; do
    if "$OLLAMA_BIN" list >/dev/null 2>&1; then
      OLLAMA_READY=true
      break
    fi
    sleep 1
  done
  [[ "$OLLAMA_READY" == true ]] || fail "Ollama server did not become ready within 30 seconds."
fi

if "$OLLAMA_BIN" show "$OLLAMA_MODEL" >/dev/null 2>&1; then
  printf 'Ollama model is ready: %s\n' "$OLLAMA_MODEL"
else
  printf 'Pulling Ollama model %s (about 4.9 GB)...\n' "$OLLAMA_MODEL"
  "$OLLAMA_BIN" pull "$OLLAMA_MODEL" || fail "Failed to pull Ollama model: $OLLAMA_MODEL"
fi

export OLLAMA_MODEL

printf 'Starting C3A AI on port 8001...\n'
(cd "$AI_DIR" && exec "$AI_PYTHON" main.py) &
PIDS+=("$!")

printf 'Starting C3A API on port 8000...\n'
(cd "$API_DIR" && exec "$API_PYTHON" main.py) &
PIDS+=("$!")

printf 'Starting C3A Expo UI...\n'
(cd "$UI_DIR" && exec npm start) &
PIDS+=("$!")

printf 'All services started with model %s. Press Ctrl+C to stop them.\n' "$OLLAMA_MODEL"
wait "${PIDS[@]}"
