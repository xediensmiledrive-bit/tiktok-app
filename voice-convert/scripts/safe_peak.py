#!/usr/bin/env python3
"""Bao dam file mp4 xuat ra khong bi clip, do tren chinh ban da encode.

Limiter chi chan dinh mau. Dinh thuc (inter-sample) va buoc encode AAC deu co
the vot len tren nguong do, nen chan o -1 dBFS truoc khi encode van co the ra
file +0.5 dBTP. Cach chac chan la do file da encode roi bu dung phan thua.

    python3 scripts/safe_peak.py audio.wav video.mp4 ra.mp4 [-1.0]
"""
import os
import re
import sys
import json
import subprocess

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import media

MAX_VONG = 3


def true_peak(path):
    p = subprocess.run(
        ["ffmpeg", "-hide_banner", "-i", path, "-af",
         "loudnorm=I=-12:TP=-1:LRA=3:print_format=json", "-f", "null", "-"],
        capture_output=True, text=True)
    m = re.search(r"\{[^{}]*input_tp[^{}]*\}", p.stderr, re.S)
    return float(json.loads(m.group(0))["input_tp"])


def mux_with_gain(video, audio, out_path, gain_db):
    af = f"volume={gain_db:.2f}dB" if abs(gain_db) > 0.01 else "anull"
    media.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
               "-i", video, "-i", audio, "-filter_complex", f"[1:a]{af}[a]",
               "-map", "0:v:0", "-map", "[a]",
               "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
               "-shortest", "-movflags", "+faststart", out_path])
    return out_path


def render(video, audio, out_path, target_tp=-1.0):
    """Ghep va lap toi da 3 vong cho den khi dinh that nam duoi target_tp."""
    gain = 0.0
    for vong in range(1, MAX_VONG + 1):
        mux_with_gain(video, audio, out_path, gain)
        tp = true_peak(out_path)
        print(f"  vong {vong}: bu {gain:+.2f} dB -> dinh that {tp:+.2f} dBTP")
        if tp <= target_tp:
            return {"gain_db": round(gain, 2), "tp": round(tp, 2), "vong": vong}
        gain += (target_tp - tp) - 0.15   # tru them chut cho lan encode sau
    return {"gain_db": round(gain, 2), "tp": round(true_peak(out_path), 2),
            "vong": MAX_VONG, "canh_bao": "chua dat nguong sau 3 vong"}


if __name__ == "__main__":
    tgt = float(sys.argv[4]) if len(sys.argv) > 4 else -1.0
    print(json.dumps(render(sys.argv[2], sys.argv[1], sys.argv[3], tgt), ensure_ascii=False))
