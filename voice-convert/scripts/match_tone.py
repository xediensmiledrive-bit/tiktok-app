#!/usr/bin/env python3
"""Can tong giong moi cho khop giong goc, do bang chinh so lieu chu khong doan.

Do nang luong theo tung dai tan cua ca hai ban (chuan hoa ve dai 300-800Hz de
bo qua to/nho), roi dung EQ bu dung phan chenh lech. Giai quyet dung cai tai
nghe ra la "nghet mui": thua tram, hut dai 2-4kHz noi phu am nam.

    python3 scripts/match_tone.py giong_moi.mp3 giong_goc.wav ra.wav
"""
import os
import sys
import subprocess

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import media

# (tan_thap, tan_cao, ten, tan_so_trung_tam_de_EQ)
BANDS = [(80, 300, "80-300", 180), (300, 800, "300-800", 500),
         (800, 2000, "800-2k", 1300), (2000, 4000, "2k-4k", 2800),
         (4000, 8000, "4k-8k", 5600), (8000, 16000, "8k-16k", 11000)]
REF = 1          # chuan hoa ve dai 300-800Hz
MAX_CORRECTION = 6.0   # khong bu qua tay, tranh nghe nhan tao


def profile(path):
    """Nang luong tung dai, chuan hoa ve dai tham chieu."""
    vals = []
    tmp = "/tmp/_mt_band.wav"
    for lo, hi, _, _ in BANDS:
        media.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                   "-i", path, "-af", f"highpass=f={lo},lowpass=f={hi}",
                   "-c:a", "pcm_s16le", tmp])
        vals.append(media.mean_volume_db(tmp))
    return [v - vals[REF] for v in vals]


def build_eq(src_profile, target_profile):
    """Chuoi filter equalizer bu phan chenh lech giua hai ban."""
    parts = []
    for i, (lo, hi, name, f0) in enumerate(BANDS):
        if i == REF:
            continue
        gain = target_profile[i] - src_profile[i]
        gain = max(-MAX_CORRECTION, min(MAX_CORRECTION, gain))
        if abs(gain) < 0.5:
            continue
        width = (hi - lo) / 2
        parts.append(f"equalizer=f={f0}:t=h:w={width:.0f}:g={gain:.2f}")
    return parts


def match(src, target, out_path, verbose=True):
    ps, pt = profile(src), profile(target)
    eq = build_eq(ps, pt)
    if verbose:
        print(f"  {'dai':>8s} {'moi':>7s} {'goc':>7s} {'bu':>7s}")
        for i, (lo, hi, n, f0) in enumerate(BANDS):
            g = 0.0 if i == REF else max(-MAX_CORRECTION,
                                         min(MAX_CORRECTION, pt[i] - ps[i]))
            print(f"  {n:>8s} {ps[i]:>7.1f} {pt[i]:>7.1f} {g:>+7.1f}")
    chain = ",".join(eq) if eq else "anull"
    media.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
               "-i", src, "-af", chain,
               "-ac", str(media.CH), "-ar", str(media.SR),
               "-c:a", "pcm_s16le", out_path])
    if verbose:
        after = profile(out_path)
        err_before = (sum((a - b) ** 2 for a, b in zip(ps, pt)) / len(ps)) ** 0.5
        err_after = (sum((a - b) ** 2 for a, b in zip(after, pt)) / len(after)) ** 0.5
        print(f"\n  lech trung binh: {err_before:.2f} dB -> {err_after:.2f} dB")
    return out_path


if __name__ == "__main__":
    match(sys.argv[1], sys.argv[2], sys.argv[3])
