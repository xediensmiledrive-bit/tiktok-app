#!/bin/bash
# Cai dat phu thuoc cho pipeline doi giong trong voice-convert/.
# Container cua moi web session la moi, nen ffmpeg phai cai lai moi lan.
set -euo pipefail

# Chi chay tren Claude Code on the web; may local tu quan phu thuoc.
if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

# --- ffmpeg (bat buoc: tach audio, canh timing, mux video) ---
if command -v ffmpeg >/dev/null 2>&1 && command -v ffprobe >/dev/null 2>&1; then
  : # da co, buoc xac minh ben duoi se in phien ban
else
  echo "Dang cai ffmpeg..."
  export DEBIAN_FRONTEND=noninteractive
  # --no-install-recommends: bo cac driver VA-API/VDPAU khong can cho xu ly headless
  apt-get update -qq
  apt-get install -y --no-install-recommends ffmpeg
fi

# Xac minh that su co ffmpeg. Khong dua vao exit code cua apt-get: loi trong $( )
# khong kich hoat set -e, nen thieu buoc nay hook se bao "san sang" du cai truot.
if ! command -v ffmpeg >/dev/null 2>&1 || ! command -v ffprobe >/dev/null 2>&1; then
  echo "LOI: cai ffmpeg xong ma van khong thay ffmpeg/ffprobe trong PATH." >&2
  echo "     Pipeline voice-convert khong chay duoc. Thu tay:" >&2
  echo "     apt-get update && apt-get install -y --no-install-recommends ffmpeg" >&2
  exit 1
fi
echo "ffmpeg: $(ffmpeg -version | head -1)"

# --- Python deps ---
REQ="${CLAUDE_PROJECT_DIR:-.}/voice-convert/requirements.txt"
if [ -f "$REQ" ]; then
  python3 -m pip install --quiet --disable-pip-version-check -r "$REQ" 2>/dev/null \
    || python3 -m pip install --quiet --break-system-packages --disable-pip-version-check -r "$REQ" \
    || echo "! Khong cai duoc python deps; kiem tra bang: python3 -c 'import requests'"
fi
python3 -c "import requests" 2>/dev/null && echo "python: requests OK" || echo "! thieu requests"

echo "Moi truong san sang cho voice-convert/."
