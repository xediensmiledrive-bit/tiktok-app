"""Cac tac vu ffmpeg: tach audio, do nang luong, keo gian timing, tron, mux."""
import os
import re
import json
import math
import shutil
import subprocess

SR = 44100
CH = 2


def run(cmd, **kw):
    """Chay ffmpeg/ffprobe, nem loi kem stderr thay vi im lang."""
    p = subprocess.run(cmd, capture_output=True, text=True, **kw)
    if p.returncode != 0:
        raise RuntimeError(
            f"Lenh that bai ({p.returncode}): {' '.join(cmd[:6])}...\n{p.stderr[-1500:]}"
        )
    return p


def require_ffmpeg():
    missing = [t for t in ("ffmpeg", "ffprobe") if not shutil.which(t)]
    if missing:
        raise RuntimeError(
            f"Thieu {', '.join(missing)}. Cai bang: apt-get update && apt-get install -y --no-install-recommends ffmpeg"
        )


# ---------------------------------------------------------------- probe

def probe(path):
    p = run(["ffprobe", "-v", "error", "-print_format", "json",
             "-show_format", "-show_streams", path])
    info = json.loads(p.stdout)
    streams = info.get("streams", [])
    return {
        "duration": float(info.get("format", {}).get("duration", 0) or 0),
        "has_audio": any(s.get("codec_type") == "audio" for s in streams),
        "has_video": any(s.get("codec_type") == "video" for s in streams),
        "streams": streams,
    }


def mean_volume_db(path):
    """Muc am trung binh (dBFS). -91 ~ im lang hoan toan."""
    p = subprocess.run(
        ["ffmpeg", "-hide_banner", "-i", path, "-af", "volumedetect",
         "-f", "null", "-"],
        capture_output=True, text=True,
    )
    m = re.search(r"mean_volume:\s*(-?\d+(?:\.\d+)?)\s*dB", p.stderr)
    return float(m.group(1)) if m else -91.0


# ---------------------------------------------------------------- extract / convert

def extract_audio(video_path, out_path):
    run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
         "-i", video_path, "-vn", "-ac", str(CH), "-ar", str(SR),
         "-c:a", "libmp3lame", "-b:a", "192k", out_path])
    return out_path


def to_wav(src, out_path):
    run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
         "-i", src, "-ac", str(CH), "-ar", str(SR),
         "-c:a", "pcm_s16le", out_path])
    return out_path


def silence_wav(duration, out_path):
    run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
         "-f", "lavfi", "-i", f"anullsrc=r={SR}:cl=stereo",
         "-t", f"{max(duration, 0.001):.4f}",
         "-c:a", "pcm_s16le", out_path])
    return out_path


# ---------------------------------------------------------------- background bed

def residual_bed(original, vocals_only, out_path):
    """original - vocals = nhac nen + tieng dong. Tru pha bang amix voi 1 kenh dao pha."""
    run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
         "-i", original, "-i", vocals_only,
         "-filter_complex",
         "[0:a]aformat=sample_rates=%d:channel_layouts=stereo[a];"
         "[1:a]aformat=sample_rates=%d:channel_layouts=stereo,volume=-1.0[b];"
         "[a][b]amix=inputs=2:duration=first:normalize=0[out]" % (SR, SR),
         "-map", "[out]", "-c:a", "pcm_s16le", out_path])
    return out_path


def has_background_music(original, vocals_only, threshold_db=12.0):
    """True neu phan con lai sau khi bo giong noi con du nang luong -> co nhac nen.

    threshold_db: khoang cach cho phep giua muc goc va muc residual.
    Residual chi thap hon ban goc <threshold_db dB => nhac nen dang ke.
    """
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tf:
        bed = tf.name
    try:
        residual_bed(original, vocals_only, bed)
        orig_db = mean_volume_db(original)
        bed_db = mean_volume_db(bed)
        gap = orig_db - bed_db
        return (gap < threshold_db), {"orig_db": orig_db, "bed_db": bed_db, "gap_db": round(gap, 2)}
    finally:
        os.path.exists(bed) and os.remove(bed)


# ---------------------------------------------------------------- timing

def duration_of(path):
    return probe(path)["duration"]


def fit_to_duration(src, out_path, target, max_stretch=1.40, min_stretch=0.95):
    """Keo/nen audio cho vua khung thoi gian target (giay), giu cao do bang atempo.

    Cau dai hon khung thi noi nhanh len, toi da max_stretch.
    Cau ngan hon khung thi chi cham lai rat nhe (min_stretch ~0.95) roi chen im lang
    cho du — de giong nghe tu nhien thay vi bi keo nhao.

    Tra ve (duration_thuc_te, ti_le_da_dung, bi_clamp_hay_khong).
    """
    cur = duration_of(src)
    if cur <= 0.01 or target <= 0.01:
        silence_wav(max(target, 0.01), out_path)
        return target, 1.0, False

    ratio = cur / target           # >1 = phai noi nhanh len
    clamped = min(max(ratio, min_stretch), max_stretch)
    was_clamped = abs(clamped - ratio) > 1e-3

    # atempo chi on trong [0.5, 2.0]; chuoi nhieu tang cho ti le ngoai khoang
    chain, r = [], clamped
    while r > 2.0:
        chain.append(2.0); r /= 2.0
    while r < 0.5:
        chain.append(0.5); r /= 0.5
    chain.append(r)
    af = ",".join(f"atempo={c:.6f}" for c in chain)

    run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
         "-i", src, "-af", af, "-ac", str(CH), "-ar", str(SR),
         "-c:a", "pcm_s16le", out_path])

    got = duration_of(out_path)
    # Ngan hon khung -> chen im lang cho khop, thay vi keo nhao giong.
    if got < target - 0.02:
        padded = out_path + ".pad.wav"
        run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
             "-i", out_path, "-af", f"apad=whole_dur={target:.4f}",
             "-c:a", "pcm_s16le", padded])
        os.replace(padded, out_path)
        got = duration_of(out_path)
    return got, clamped, was_clamped


def pad_to_duration(src, out_path, target):
    """Keo dai audio bang im lang cho du target giay (khong lam ngan neu dang dai hon).

    Can thiet vi mux dung -shortest: track giong ngan hon video se cat cut hinh.
    """
    cur = duration_of(src)
    if cur >= target - 0.02:
        if src != out_path:
            run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                 "-i", src, "-c:a", "pcm_s16le", out_path])
        return duration_of(out_path)
    run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
         "-i", src, "-af", f"apad=whole_dur={target:.4f}",
         "-ac", str(CH), "-ar", str(SR), "-c:a", "pcm_s16le", out_path])
    return duration_of(out_path)


def concat_wavs(paths, out_path):
    """Noi cac wav cung dinh dang theo thu tu."""
    lst = out_path + ".txt"
    with open(lst, "w") as f:
        for p in paths:
            f.write(f"file '{os.path.abspath(p)}'\n")
    run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
         "-f", "concat", "-safe", "0", "-i", lst,
         "-c:a", "pcm_s16le", "-ac", str(CH), "-ar", str(SR), out_path])
    os.remove(lst)
    return out_path


def mix_tracks(voice, bed, out_path, bed_gain_db=-3.0):
    """Tron giong moi voi nhac nen. duong dan bed=None -> chi copy voice."""
    if not bed:
        return to_wav(voice, out_path)
    run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
         "-i", voice, "-i", bed,
         "-filter_complex",
         f"[1:a]volume={bed_gain_db}dB[b];"
         f"[0:a][b]amix=inputs=2:duration=first:normalize=0,"
         f"alimiter=limit=0.95[out]",
         "-map", "[out]", "-c:a", "pcm_s16le", out_path])
    return out_path


def mux(video_path, audio_path, out_path):
    """Gan track audio moi vao video, khong re-encode hinh."""
    run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
         "-i", video_path, "-i", audio_path,
         "-map", "0:v:0", "-map", "1:a:0",
         "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
         "-shortest", "-movflags", "+faststart", out_path])
    return out_path
