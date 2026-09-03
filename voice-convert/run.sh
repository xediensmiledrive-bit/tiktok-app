#!/usr/bin/env bash
# Chay toan bo pipeline doi giong cho moi clip trong input/
set -euo pipefail
cd "$(dirname "$0")"

if ! command -v ffmpeg >/dev/null 2>&1; then
  echo ">> Chua co ffmpeg, dang cai..."
  apt-get update -qq && apt-get install -y --no-install-recommends ffmpeg
fi

python3 scripts/preflight.py || {
  echo ">> Preflight bao loi, dung lai."
  exit 1
}

exec python3 scripts/pipeline.py "$@"
