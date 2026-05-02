#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN="${PYTHON_BIN:-}"
VENV_DIR="${OPEN_NOTEBOOK_VENV:-.venv311}"
PIP_INDEX_URL="${PIP_INDEX_URL:-https://pypi.tuna.tsinghua.edu.cn/simple}"
HOST="${OPEN_NOTEBOOK_HOST:-127.0.0.1}"
PORT="${OPEN_NOTEBOOK_PORT:-8017}"
SYSTEM_NAME="$(uname -s 2>/dev/null || printf unknown)"
DEFAULT_U1_DEVICE="cuda"
if [[ "$SYSTEM_NAME" == "Darwin" ]]; then
  DEFAULT_U1_DEVICE="mps"
fi

find_python311() {
  if [[ -n "$PYTHON_BIN" ]]; then
    printf '%s\n' "$PYTHON_BIN"
    return 0
  fi
  for candidate in python3.11 python3 python; do
    if command -v "$candidate" >/dev/null 2>&1; then
      if "$candidate" - <<'PY' >/dev/null 2>&1
import sys
raise SystemExit(0 if sys.version_info[:2] == (3, 11) else 1)
PY
      then
        printf '%s\n' "$candidate"
        return 0
      fi
    fi
  done
  return 1
}

if [[ ! -x "$VENV_DIR/bin/python" ]]; then
  if ! PYTHON_BIN="$(find_python311)"; then
    echo "Python 3.11 was not found. Install Python 3.11 first, or set PYTHON_BIN=/path/to/python3.11." >&2
    exit 1
  fi
  echo "[Open_Notebook] Creating virtual environment: $VENV_DIR"
  "$PYTHON_BIN" -m venv "$VENV_DIR"
fi

PY="$VENV_DIR/bin/python"

if ! "$PY" - <<'PY' >/dev/null 2>&1
import sys
raise SystemExit(0 if sys.version_info[:2] == (3, 11) else 1)
PY
then
  echo "$VENV_DIR is not a Python 3.11 environment. Remove it or set OPEN_NOTEBOOK_VENV to a Python 3.11 venv." >&2
  exit 1
fi

if ! "$PY" - <<'PY' >/dev/null 2>&1
import fastapi, uvicorn, open_notebook
PY
then
  echo "[Open_Notebook] Installing Python dependencies with Tsinghua mirror..."
  "$PY" -m pip install -U pip -i "$PIP_INDEX_URL"
  "$PY" -m pip install -e ".[local-u1]" -i "$PIP_INDEX_URL"
fi

export OPEN_NOTEBOOK_HOST="$HOST"
export OPEN_NOTEBOOK_PORT="$PORT"
export OPEN_NOTEBOOK_DATA_DIR="${OPEN_NOTEBOOK_DATA_DIR:-data}"
export SENSENOVA_U1_MODEL_PATH="${SENSENOVA_U1_MODEL_PATH:-models/Full}"
export SENSENOVA_U1_SOURCE_ROOT="${SENSENOVA_U1_SOURCE_ROOT:-../SenseNova-U1-main/src}"
export SENSENOVA_U1_DEVICE="${SENSENOVA_U1_DEVICE:-$DEFAULT_U1_DEVICE}"
export SENSENOVA_U1_DTYPE="${SENSENOVA_U1_DTYPE:-bfloat16}"
export SENSENOVA_U1_NUM_STEPS="${SENSENOVA_U1_NUM_STEPS:-50}"
export SENSENOVA_U1_CFG_SCALE="${SENSENOVA_U1_CFG_SCALE:-4.0}"
export SENSENOVA_U1_CFG_NORM="${SENSENOVA_U1_CFG_NORM:-none}"
export SENSENOVA_U1_TIMESTEP_SHIFT="${SENSENOVA_U1_TIMESTEP_SHIFT:-3.0}"
export SENSENOVA_U1_CFG_INTERVAL="${SENSENOVA_U1_CFG_INTERVAL:-0.0,1.0}"
export SENSENOVA_U1_BATCH_SIZE="${SENSENOVA_U1_BATCH_SIZE:-1}"
export SENSENOVA_U1_SEED="${SENSENOVA_U1_SEED:-42}"

ARGS=("--host" "$HOST" "--port" "$PORT")
for arg in "$@"; do
  case "$arg" in
    --host|--port)
      echo "Pass host/port through OPEN_NOTEBOOK_HOST and OPEN_NOTEBOOK_PORT when using start_webui.sh." >&2
      exit 1
      ;;
  esac
done
if [[ "${OPEN_NOTEBOOK_NO_OPEN:-0}" == "1" || " $* " == *" --no-open "* ]]; then
  ARGS+=("--no-open")
fi
if [[ "${OPEN_NOTEBOOK_FAKE_IMAGE:-0}" == "1" || " $* " == *" --fake-image "* ]]; then
  ARGS+=("--fake-image")
elif [[ " $* " == *" --api-image "* ]]; then
  ARGS+=("--api-image")
elif [[ -f "$SENSENOVA_U1_MODEL_PATH/config.json" && -f "$SENSENOVA_U1_MODEL_PATH/model.safetensors.index.json" ]]; then
  ARGS+=("--local-u1")
fi

echo "[Open_Notebook] Web UI: http://$HOST:$PORT"
echo "[Open_Notebook] Model path: $SENSENOVA_U1_MODEL_PATH"
echo "[Open_Notebook] U1 source:   $SENSENOVA_U1_SOURCE_ROOT"
exec "$PY" start.py "${ARGS[@]}"
