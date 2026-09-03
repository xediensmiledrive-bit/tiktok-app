#!/usr/bin/env python3
"""Kiem tra moi thu san sang truoc khi chay pipeline."""
import os
import sys
import json
import shutil

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

OK, BAD = "[OK]  ", "[LOI] "
problems = []


def check(name, cond, fix=""):
    print(f"{OK if cond else BAD}{name}")
    if not cond:
        if fix:
            print(f"       -> {fix}")
        problems.append(name)
    return cond


print("=== Kiem tra moi truong ===")
check("ffmpeg + ffprobe", bool(shutil.which("ffmpeg") and shutil.which("ffprobe")),
      "apt-get update && apt-get install -y --no-install-recommends ffmpeg")

has_key = bool(os.environ.get("ELEVENLABS_API_KEY", "").strip())
check("ELEVENLABS_API_KEY", has_key, "export ELEVENLABS_API_KEY=xi_...")

cfg_path = os.path.join(ROOT, "config.json")
voice_ok = False
if check("config.json ton tai", os.path.exists(cfg_path)):
    cfg = json.load(open(cfg_path, encoding="utf-8"))
    vid = (cfg.get("voice_id") or "").strip()
    voice_ok = check("voice_id da chon", bool(vid) and not vid.startswith("<"),
                     "python3 scripts/list_voices.py --add")

print("\n=== Ket noi ElevenLabs ===")
net_ok = False
if has_key:
    try:
        import el_api
        voices = el_api.list_my_voices()
        net_ok = check(f"goi API duoc ({len(voices)} giong trong tai khoan)", True)
    except Exception as e:
        msg = str(e)[:200]
        check("goi API duoc", False,
              "Neu la loi mang/403 CONNECT: host api.elevenlabs.io chua duoc mo trong "
              "network policy cua environment.\n          Chi tiet: " + msg)
else:
    print("       (bo qua — chua co key)")

n_in = len([f for f in os.listdir(os.path.join(ROOT, "input"))
            if os.path.splitext(f)[1].lower() in
            {".mp4", ".mov", ".mkv", ".webm", ".m4v", ".avi"}]) \
    if os.path.isdir(os.path.join(ROOT, "input")) else 0
print(f"\n=== Clip dau vao ===\n{OK if n_in else '[?]   '}{n_in} clip trong input/")

print()
if problems:
    print(f"Con {len(problems)} viec can xu ly: {', '.join(problems)}")
    sys.exit(1)
print("San sang. Chay: ./run.sh")
