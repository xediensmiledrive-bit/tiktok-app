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


def _shrink(src, out_path, target, workdir, noise_db, min_dur, floor=0.14,
            max_stretch=1.40):
    """Ban doc dai hon khung: cat bot khoang nghi, phan con lai bu bang atempo."""
    tmp = os.path.join(workdir, "_fits")
    os.makedirs(tmp, exist_ok=True)
    cur = media.duration_of(src)

    pauses = [(s, e) for s, e in find_pauses(src, noise_db, min_dur) if e < cur - 0.15]
    if not pauses:
        got, ratio, _ = media.fit_to_duration(src, out_path, target)
        return {"cach": "atempo (khong co khoang nghi de cat)",
                "ti_le": round(ratio, 4), "ra": round(got, 3)}

    # Cat moi khoang nghi xuong floor, nhung khong cat qua muc can thiet
    excess = cur - target
    trimmable = sum(max(0.0, (e - s) - floor) for s, e in pauses)
    share = min(1.0, excess / trimmable) if trimmable > 0 else 0.0

    pieces, cursor = [], 0.0
    for i, (s, e) in enumerate(pauses):
        # Ban doc co the mo dau bang im lang (s = 0), hoac silencedetect tra ve
        # hai khoang nghi dinh nhau (s == e cua khoang truoc). Ca hai truong hop
        # deu cho doan tieng dai 0 giay -> ffmpeg bao "-to value smaller than -ss".
        if s - cursor > 0.01:
            seg = os.path.join(tmp, f"a{i:03d}.wav")
            media.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                       "-ss", f"{cursor:.4f}", "-to", f"{s:.4f}", "-i", src,
                       "-ac", str(media.CH), "-ar", str(media.SR),
                       "-c:a", "pcm_s16le", seg])
            pieces.append(seg)
        keep = (e - s) - max(0.0, (e - s) - floor) * share
        gap = os.path.join(tmp, f"g{i:03d}.wav")
        pieces.append(media.silence_wav(max(keep, 0.02), gap))
        cursor = e

    tail = os.path.join(tmp, "tail.wav")
    media.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
               "-ss", f"{cursor:.4f}", "-i", src,
               "-ac", str(media.CH), "-ar", str(media.SR),
               "-c:a", "pcm_s16le", tail])
    pieces.append(tail)

    joined = media.concat_wavs(pieces, os.path.join(tmp, "joined.wav"))
    after_trim = media.duration_of(joined)
    got, ratio, clamped = media.fit_to_duration(joined, out_path, target,
                                                max_stretch=max_stretch)
    ra = media.duration_of(out_path)
    out = {
        "cach": "cat khoang nghi + noi nhanh",
        "so_khoang_nghi": len(pauses),
        "sau_khi_cat_nghi": round(after_trim, 2),
        "ti_le_noi_nhanh": round(ratio, 4),
        "bi_gioi_han": clamped,
        "ra": round(ra, 3),
    }
    # Khong nhet vua: mux dung -shortest nen phan thua se bi CAT MAT TIENG,
    # ma cat im lang khong bao gi. Phai bao to o day.
    if ra > target + 0.3:
        out["LOI"] = (f"audio dai hon video {ra - target:.2f}s — se bi cat mat tieng. "
                      f"Can noi nhanh {after_trim / target:.2f}x nhung tran dang la "
                      f"{max_stretch:.2f}x. Nang max_stretch, ha floor, hoac rut gon loi.")
    return out


def fit(src, out_path, target, workdir=None, noise_db=-40, min_dur=0.12,
        max_extra_per_pause=1.2, floor=0.14, max_stretch=1.40):
    """Keo dai cac khoang nghi cho tong thoi luong bang target.

    Neu khong du khoang nghi de gian, phan con lai duoc bu bang atempo nhe.
    Tra ve dict mo ta da lam gi.
    """
    cur = media.duration_of(src)
    deficit = target - cur
    workdir = workdir or os.path.dirname(out_path) or "."
    tmp = os.path.join(workdir, "_fitp")
    os.makedirs(tmp, exist_ok=True)

    if deficit < -0.02:
        # Ban doc DAI hon khung -> cat bot khoang nghi truoc, con thieu moi noi nhanh.
        # Cat nghi truoc giup ti le atempo nho lai, giong do bi nghe nhu tua bang.
        return _shrink(src, out_path, target, workdir, noise_db, min_dur,
                       floor=floor, max_stretch=max_stretch)

    if abs(deficit) <= 0.02:
        got, ratio, clamped = media.fit_to_duration(src, out_path, target)
        return {"cach": "khong can chinh", "ti_le": round(ratio, 4), "ra": round(got, 3)}

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
        # Ban doc co the mo dau bang im lang (s = 0), hoac silencedetect tra ve
        # hai khoang nghi dinh nhau (s == e cua khoang truoc). Ca hai truong hop
        # deu cho doan tieng dai 0 giay -> ffmpeg bao "-to value smaller than -ss".
        if s - cursor > 0.01:
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
    kw = {}
    if len(sys.argv) > 4: kw["floor"] = float(sys.argv[4])
    if len(sys.argv) > 5: kw["max_stretch"] = float(sys.argv[5])
    info = fit(src, out, target, **kw)
    for k, v in info.items():
        print(f"  {k}: {v}")
