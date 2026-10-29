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
SPEECH_COMPOSE_FILE="$CORE_DIR/docker-compose.speech.yml"
SPEECH_HEALTH_URL="http://127.0.0.1:8002/health"
C3A_SPEECH_MODELS_DIR="${C3A_SPEECH_MODELS_DIR:-$HOME/.c3a/models}"
export C3A_SPEECH_MODELS_DIR
CHECK_ONLY=false
ENV_SOURCE_DIR=""

# Usage: ./<launcher> [--check] [ENV_FOLDER]
# ENV_FOLDER holds .env files laid out like this repository, e.g.
# ENV_FOLDER/c3a-core/c3a-core-api/.env; they are copied in before startup.
for arg in "$@"; do
  case "$arg" in
    --check) CHECK_ONLY=true ;;
    -*) printf 'ERROR: Unknown option: %s\n' "$arg" >&2; exit 2 ;;
    *)
      [[ -z "$ENV_SOURCE_DIR" ]] || { printf 'ERROR: Only one environment folder may be given.\n' >&2; exit 2; }
      ENV_SOURCE_DIR="$arg"
      ;;
  esac
done

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
  local sync_args=(--root "$SCRIPT_DIR")
  [[ "$CHECK_ONLY" == true ]] && sync_args+=(--check)
  [[ -n "$ENV_SOURCE_DIR" ]] && sync_args+=(--import-from "$ENV_SOURCE_DIR")
  if output="$("$API_PYTHON" "$ENV_SYNC_SCRIPT" "${sync_args[@]}" 2>&1)"; then
    printf '%s\n' "$output"
    return 0
  fi
  [[ -n "$output" ]] || output="Environment validation failed without an error message."
  fail "${output#ERROR: }"
}

validate_speech_models() {
  local encoder="$C3A_SPEECH_MODELS_DIR/whisper-base/base-encoder.int8.onnx"
  local decoder="$C3A_SPEECH_MODELS_DIR/whisper-base/base-decoder.int8.onnx"
  local tokens="$C3A_SPEECH_MODELS_DIR/whisper-base/base-tokens.txt"
  local size

  [[ -f "$encoder" ]] || fail "Whisper encoder not found: $encoder"
  [[ -f "$decoder" ]] || fail "Whisper decoder not found: $decoder"
  [[ -f "$tokens" ]] || fail "Whisper tokens not found: $tokens"
  size="$(wc -c < "$encoder")" || fail "Unable to read Whisper encoder: $encoder"
  (( size >= 20000000 )) || fail "Whisper encoder is incomplete or corrupt: $encoder"
  size="$(wc -c < "$decoder")" || fail "Unable to read Whisper decoder: $decoder"
  (( size >= 100000000 )) || fail "Whisper decoder is incomplete or corrupt: $decoder"
  size="$(wc -c < "$tokens")" || fail "Unable to read Whisper tokens: $tokens"
  (( size >= 500000 )) || fail "Whisper tokens file is incomplete or corrupt: $tokens"
}

speech_is_healthy() {
  "$API_PYTHON" - "$SPEECH_HEALTH_URL" >/dev/null 2>&1 <<'PY'
import json
import sys
import urllib.request

with urllib.request.urlopen(sys.argv[1], timeout=3) as response:
    payload = json.load(response)
if not (
    payload.get("enabled")
    and payload.get("loaded")
    and payload.get("backend") == "whisper_onnx"
    and payload.get("model") == "whisper-base-int8"
):
    raise SystemExit(1)
PY
}

wait_for_docker() {
  local attempt
  for ((attempt = 1; attempt <= 180; attempt++)); do
    "$DOCKER_BIN" info >/dev/null 2>&1 && return 0
    sleep 1
  done
  return 1
}

wait_for_speech() {
  local attempt
  for ((attempt = 1; attempt <= 120; attempt++)); do
    speech_is_healthy && return 0
    sleep 1
  done
  return 1
}

ensure_speech_service() {
  if speech_is_healthy; then
    printf 'Speech service is already healthy on port 8002.\n'
    return 0
  fi
  if ! "$DOCKER_BIN" info >/dev/null 2>&1; then
    [[ -d "/Applications/Docker.app" ]] || fail \
      "Docker daemon is not running and Docker Desktop was not found in /Applications."
    command -v open >/dev/null 2>&1 || fail "macOS open command is unavailable; start Docker Desktop manually."
    printf 'Starting Docker Desktop...\n'
    open -gj -a Docker || fail "Failed to open Docker Desktop."
    wait_for_docker || fail \
      "Docker Desktop did not become ready within 3 minutes. Open it, accept any first-run prompt, and retry."
  fi
  printf 'Building and starting the local speech service...\n'
  "$DOCKER_BIN" compose -f "$SPEECH_COMPOSE_FILE" up -d --build || \
    fail "Failed to build or start the local speech container."
  if ! wait_for_speech; then
    "$DOCKER_BIN" compose -f "$SPEECH_COMPOSE_FILE" logs --tail 40 c3a-speech || true
    fail "Speech service did not load its models within 2 minutes."
  fi
  printf 'Speech service is healthy and its models are loaded.\n'
}

[[ -f "$UI_DIR/package.json" ]] || fail "UI entrypoint not found: $UI_DIR/package.json"
[[ -f "$API_DIR/main.py" ]] || fail "API entrypoint not found: $API_DIR/main.py"
[[ -f "$AI_DIR/main.py" ]] || fail "AI entrypoint not found: $AI_DIR/main.py"
[[ -f "$API_DIR/requirements.txt" ]] || fail "API requirements not found: $API_DIR/requirements.txt"
[[ -f "$AI_DIR/requirements.txt" ]] || fail "AI requirements not found: $AI_DIR/requirements.txt"
[[ -f "$ENV_SYNC_SCRIPT" ]] || fail "Environment checker not found: $ENV_SYNC_SCRIPT"
[[ -f "$SPEECH_COMPOSE_FILE" ]] || fail "Speech Compose file not found: $SPEECH_COMPOSE_FILE"
[[ -f "$AI_DIR/Dockerfile.speech" ]] || fail "Speech Dockerfile not found: $AI_DIR/Dockerfile.speech"
[[ -f "$AI_DIR/requirements.speech.txt" ]] || fail "Speech requirements not found: $AI_DIR/requirements.speech.txt"
DOCKER_BIN="$(command -v docker || true)"
if [[ -z "$DOCKER_BIN" && -x "/Applications/Docker.app/Contents/Resources/bin/docker" ]]; then
  DOCKER_BIN="/Applications/Docker.app/Contents/Resources/bin/docker"
  DOCKER_BIN_DIR="$(dirname "$DOCKER_BIN")"
  export PATH="$DOCKER_BIN_DIR:$PATH"
fi
[[ -n "$DOCKER_BIN" ]] || fail "Docker was not found. Install Docker Desktop first."
"$DOCKER_BIN" --version >/dev/null 2>&1 || fail "Docker was found but could not run."
"$DOCKER_BIN" compose version >/dev/null 2>&1 || fail "Docker Compose is unavailable. Repair or update Docker Desktop."
validate_speech_models
"$DOCKER_BIN" compose -f "$SPEECH_COMPOSE_FILE" config --quiet >/dev/null 2>&1 || \
  fail "Speech Compose configuration is invalid. Check C3A_SPEECH_MODELS_DIR and docker-compose.speech.yml."
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

if [[ "$CHECK_ONLY" == true ]]; then
  run_env_sync
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
  printf 'Docker:     %s (%s)\n' "$DOCKER_BIN" "$("$DOCKER_BIN" --version)"
  printf 'Compose:    %s\n' "$("$DOCKER_BIN" compose version --short 2>/dev/null || "$DOCKER_BIN" compose version)"
  printf 'Speech models: %s\n' "$C3A_SPEECH_MODELS_DIR"
  if "$DOCKER_BIN" info >/dev/null 2>&1; then
    printf 'Docker daemon: running\n'
  else
    printf 'Docker daemon: not running; normal startup will open Docker Desktop\n'
  fi
  if speech_is_healthy; then
    printf 'Speech service: healthy and models loaded\n'
  else
    printf 'Speech service: not ready; normal startup will build or start it\n'
  fi
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

ensure_speech_service

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

printf 'All services started with model %s. Speech is healthy on port 8002. Press Ctrl+C to stop them.\n' "$OLLAMA_MODEL"
wait "${PIDS[@]}"
