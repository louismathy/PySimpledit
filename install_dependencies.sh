#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

echo "[Simpledit] Starting setup ..."

if [ ! -d "venv" ]; then
  echo "[Simpledit] Create virtual environment ..."
  python3 -m venv venv
fi

# shellcheck disable=SC1091
source venv/bin/activate

echo "[Simpledit] Install dependencies ..."
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

if ! command -v ffmpeg >/dev/null 2>&1; then
  echo ""
  echo "[Note] ffmpeg not found. Please install and add to PATH."
  echo "       Download: https://ffmpeg.org/download.html"
  echo ""
fi

echo "[Simpledit] Dependencies installed."
