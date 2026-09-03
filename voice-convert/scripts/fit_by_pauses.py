#!/usr/bin/env python3
"""Gian audio cho vua khung thoi gian bang cach keo dai cac khoang nghi.

Dung khi ban doc moi NGAN hon video. Hai cach xu ly thong thuong deu do:
  - lam cham giong (atempo < 1): nghe i, nhao;
  - chen im lang o cuoi: clip het tieng may giay cuoi.
Cach nay giu nguyen toc do noi, chi them hoi tho giua cau — giong lam long tieng that.

    python3 scripts/fit_by_pauses.py vao.mp3 ra.wav 65.0
"""
import os
import re
import sys
import subprocess

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import media


def find_pauses(path, noise_db=-40, min_dur=0.12):
    """Tra ve [(start, end)] cac khoang nghi phat hien duoc."""
    p = subprocess.run(
        ["ffmpeg", "-hide_banner", "-i", path, "-af",
         f"silencedetect=noise={noise_db}dB:d={min_dur}", "-f", "null", "-"],
        capture_output=True, text=True)
    starts = [float(x) for x in re.findall(r"silence_start:\s*(-?[\d.]+)", p.stderr)]
    ends = [float(x) for x in re.findall(r"silence_end:\s*([\d.]+)", p.stderr)]
    return list(zip(starts, ends))[:len(ends)]


def fit(src, out_path, target, workdir=None, noise_db=-40, min_dur=0.12,
        max_extra_per_pause=1.2):
    """Keo dai cac khoang nghi cho tong thoi luong bang target.

    Neu khong du khoang nghi de gian, phan con lai duoc bu bang atempo nhe.
    Tra ve dict mo ta da lam gi.
    """
    cur = media.duration_of(src)
    deficit = target - cur
    workdir = workdir or os.path.dirname(out_path) or "."
    tmp = os.path.join(workdir, "_fitp")
    os.makedirs(tmp, exist_ok=True)

    if deficit <= 0.02:
        # Da du dai hoac dai hon -> dung cach thong thuong
        got, ratio, clamped = media.fit_to_duration(src, out_path, target)
        return {"cach": "atempo", "ti_le": round(ratio, 4), "ra": round(got, 3)}

    pauses = find_pauses(src, noise_db, min_dur)
    # Bo khoang nghi dinh vao duoi file: keo dai no chi tao im lang cuoi clip
    pauses = [(s, e) for s, e in pauses if e < cur - 0.15]
    if not pauses:
        got, ratio, clamped = media.fit_to_duration(src, out_path, target)
        return {"cach": "atempo (khong tim thay khoang nghi)",
                "ti_le": round(ratio, 4), "ra": round(got, 3)}

    extra = deficit / len(pauses)
    capped = min(extra, max_extra_per_pause)

    pieces, cursor = [], 0.0
    for i, (s, e) in enumerate(pauses):
        seg = os.path.join(tmp, f"a{i:03d}.wav")
        media.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                   "-ss", f"{cursor:.4f}", "-to", f"{s:.4f}", "-i", src,
                   "-ac", str(media.CH), "-ar", str(media.SR),
                   "-c:a", "pcm_s16le", seg])
        pieces.append(seg)
        gap = os.path.join(tmp, f"g{i:03d}.wav")
        pieces.append(media.silence_wav((e - s) + capped, gap))
        cursor = e

    tail = os.path.join(tmp, "tail.wav")
    media.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
               "-ss", f"{cursor:.4f}", "-i", src,
               "-ac", str(media.CH), "-ar", str(media.SR),
               "-c:a", "pcm_s16le", tail])
    pieces.append(tail)

    joined = os.path.join(tmp, "joined.wav")
    media.concat_wavs(pieces, joined)

    # Con lech thi bu not bang atempo rat nhe / pad
    got, ratio, _ = media.fit_to_duration(joined, out_path, target, min_stretch=0.90)
    return {
        "cach": "gian khoang nghi",
        "so_khoang_nghi": len(pauses),
        "them_moi_khoang": round(capped, 3),
        "ti_le_atempo_bu": round(ratio, 4),
        "ra": round(media.duration_of(out_path), 3),
    }


if __name__ == "__main__":
    src, out, target = sys.argv[1], sys.argv[2], float(sys.argv[3])
    info = fit(src, out, target)
    for k, v in info.items():
        print(f"  {k}: {v}")
