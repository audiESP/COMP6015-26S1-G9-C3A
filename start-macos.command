#!/usr/bin/env bash

set -u

# Finder-launched .command files do not always inherit Homebrew's PATH.
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CORE_DIR="$SCRIPT_DIR/c3a-core"
UI_DIR="$CORE_DIR/c3a-core-ui"
API_DIR="$CORE_DIR/c3a-core-api"
AI_DIR="$CORE_DIR/c3a-core-ai"
ENV_SYNC_SCRIPT="$SCRIPT_DIR/tools/sync_env.py"
OLLAMA_MODEL="llama3.1:8b-instruct-q4_K_M"

show_warning() {
  if command -v osascript >/dev/null 2>&1; then
    C3A_WARNING_MESSAGE="$1" osascript \
      -e 'display alert "C3A Startup Warning" message (system attribute "C3A_WARNING_MESSAGE") as warning buttons {"OK"} default button "OK"' \
      >/dev/null 2>&1 || true
  fi
}

fail() {
  printf 'ERROR: %s\n' "$1" >&2
  show_warning "$1"
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

run_env_sync() {
  local output
  if [[ "${1:-}" == "--check" ]]; then
    if output="$("$API_PYTHON" "$ENV_SYNC_SCRIPT" --root "$SCRIPT_DIR" --check 2>&1)"; then
      printf '%s\n' "$output"
      return 0
    fi
  else
    if output="$("$API_PYTHON" "$ENV_SYNC_SCRIPT" --root "$SCRIPT_DIR" 2>&1)"; then
      printf '%s\n' "$output"
      return 0
    fi
  fi
  [[ -n "$output" ]] || output="Environment validation failed without an error message."
  fail "${output#ERROR: }"
}

[[ -f "$UI_DIR/package.json" ]] || fail "UI entrypoint not found: $UI_DIR/package.json"
[[ -f "$API_DIR/main.py" ]] || fail "API entrypoint not found: $API_DIR/main.py"
[[ -f "$AI_DIR/main.py" ]] || fail "AI entrypoint not found: $AI_DIR/main.py"
[[ -f "$API_DIR/requirements.txt" ]] || fail "API requirements not found: $API_DIR/requirements.txt"
[[ -f "$AI_DIR/requirements.txt" ]] || fail "AI requirements not found: $AI_DIR/requirements.txt"
[[ -f "$ENV_SYNC_SCRIPT" ]] || fail "Environment checker not found: $ENV_SYNC_SCRIPT"
command -v node >/dev/null 2>&1 || fail "Node.js was not found on PATH. Install Node.js first."
command -v npm >/dev/null 2>&1 || fail "npm was not found on PATH. Install Node.js first."
node --version >/dev/null 2>&1 || fail "Node.js was found but could not run."
npm --version >/dev/null 2>&1 || fail "npm was found but could not run."

OLLAMA_BIN="$(command -v ollama || true)"
if [[ -z "$OLLAMA_BIN" && -x "/Applications/Ollama.app/Contents/Resources/ollama" ]]; then
  OLLAMA_BIN="/Applications/Ollama.app/Contents/Resources/ollama"
fi
[[ -n "$OLLAMA_BIN" ]] || fail "Ollama was not found. Install the Ollama app first."

API_PYTHON="$(find_python "$API_DIR")" || fail "Python 3 was not found. Create .venv here or install Python 3."
AI_PYTHON="$(find_python "$AI_DIR")" || fail "Python 3 was not found. Create .venv here or install Python 3."
"$API_PYTHON" -m pip --version >/dev/null 2>&1 || fail "pip is unavailable for the API Python environment."
"$AI_PYTHON" -m pip --version >/dev/null 2>&1 || fail "pip is unavailable for the AI Python environment."

if [[ "${1:-}" == "--check" ]]; then
  run_env_sync --check
  printf 'C3A startup preflight passed.\n'
  printf 'API Python: %s\n' "$API_PYTHON"
  printf 'AI Python:  %s\n' "$AI_PYTHON"
  printf 'Node.js:    %s (%s)\n' "$(command -v node)" "$(node --version)"
  printf 'npm:        %s (%s)\n' "$(command -v npm)" "$(npm --version)"
  printf 'Python requirements: found; normal startup will install them\n'
  if [[ -d "$UI_DIR/node_modules" ]] && (cd "$UI_DIR" && npm ls --depth=0 >/dev/null 2>&1); then
    printf 'UI dependencies: installed and valid\n'
  else
    printf 'UI dependencies: missing or invalid; normal startup will run npm ci\n'
  fi
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

run_env_sync

printf 'Installing API Python requirements...\n'
"$API_PYTHON" -m pip install -r "$API_DIR/requirements.txt" || fail "Failed to install API Python requirements."

printf 'Installing AI Python requirements...\n'
"$AI_PYTHON" -m pip install -r "$AI_DIR/requirements.txt" || fail "Failed to install AI Python requirements."

if [[ -d "$UI_DIR/node_modules" ]] && (cd "$UI_DIR" && npm ls --depth=0 >/dev/null 2>&1); then
  printf 'UI dependencies are installed and valid.\n'
else
  printf 'Installing UI dependencies...\n'
  if [[ -f "$UI_DIR/package-lock.json" ]]; then
    (cd "$UI_DIR" && npm ci) || fail "Failed to install UI dependencies with npm ci."
  else
    (cd "$UI_DIR" && npm install) || fail "Failed to install UI dependencies with npm install."
  fi
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
