#!/usr/bin/env python3
"""Bao dam file mp4 xuat ra khong bi clip, do tren chinh ban da encode.

Limiter chi chan dinh mau. Dinh thuc (inter-sample) va buoc encode AAC deu co
the vot len tren nguong do, nen chan o -1 dBFS truoc khi encode van co the ra
file +0.5 dBTP. Cach chac chan la do file da encode roi ha gain di.

Va phai do tung buoc: dinh sau encode khong don dieu theo gain (xem render).

    python3 scripts/safe_peak.py audio.wav video.mp4 ra.mp4 [-1.0]
"""
import os
import re
import sys
import json
import subprocess

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import media



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


def render(video, audio, out_path, target_tp=-1.0, step=0.5, max_thu=14):
    """Ghep va ha gain cho den khi dinh that nam duoi target_tp.

    KHONG noi suy. Do thuc te tren clip nay cho thay dinh that sau khi encode
    AAC KHONG don dieu theo gain — no dao dong toi +-1.5 dB voi nhung buoc gain
    rat nho:
        -2.4 dB -> -1.66 dBTP
        -2.5 dB -> -0.88 dBTP
        -2.6 dB -> +0.47 dBTP   <- vot len du gain thap hon
        -2.7 dB -> -1.46 dBTP
        -2.8 dB -> -2.35 dBTP
    Bo ma hoa phan bo bit khac nhau theo muc vao, nen dinh giai ma nhay loan.
    Noi suy tren mot ham nhu vay khong bao gio hoi tu. Cach chac chan la do tung
    buoc co dinh di xuong va lay gain dau tien dat nguong.

    step  : buoc ha gain moi lan (dB)
    """
    # Uoc luong buoc dau cho do ton vong, roi do tung buoc tu do
    mux_with_gain(video, audio, out_path, 0.0)
    tp = true_peak(out_path)
    print(f"  bu  +0.00 dB -> {tp:+.2f} dBTP")
    if tp <= target_tp:
        return {"gain_db": 0.0, "tp": round(tp, 2), "so_lan_do": 1}

    gain = round((target_tp - tp) / step) * step   # bam vao luoi buoc
    best = (tp, 0.0)
    for lan in range(2, max_thu + 1):
        mux_with_gain(video, audio, out_path, gain)
        tp = true_peak(out_path)
        print(f"  bu {gain:+6.2f} dB -> {tp:+.2f} dBTP")
        if tp < best[0]:
            best = (tp, gain)
        if tp <= target_tp:
            return {"gain_db": round(gain, 2), "tp": round(tp, 2), "so_lan_do": lan}
        gain -= step

    mux_with_gain(video, audio, out_path, best[1])
    tp = true_peak(out_path)
    return {"gain_db": round(best[1], 2), "tp": round(tp, 2), "so_lan_do": max_thu,
            "canh_bao": f"chua xuong duoi {target_tp} dBTP"}


if __name__ == "__main__":
    tgt = float(sys.argv[4]) if len(sys.argv) > 4 else -1.0
    print(json.dumps(render(sys.argv[2], sys.argv[1], sys.argv[3], tgt), ensure_ascii=False))
