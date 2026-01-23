#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

if [ ! -d "venv" ]; then
  echo "[Simpledit] Missing virtual environment. Run install_dependencies.sh first."
  exit 1
fi

# shellcheck disable=SC1091
source venv/bin/activate

echo "[Simpledit] Starting editor ..."
python src/main.py
