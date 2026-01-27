#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

if [ ! -d "venv" ]; then
  echo "[Simpledit] Missing virtual environment. Run install_dependencies.sh first."
  exit 1
fi

# shellcheck disable=SC1091
source venv/bin/activate

# Debug logging (optional)
# export SIMPLEDIT_DEBUG=1
if [ "${SIMPLEDIT_DEBUG:-}" = "1" ]; then
  export SIMPLEDIT_DEBUG_FILE="$(pwd)/simpledit-debug.log"
fi

echo "[Simpledit] Starting editor ..."
python src/main.py
