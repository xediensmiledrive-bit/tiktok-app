#!/usr/bin/env python3
"""Tron nhac nen duoi giong doc, co ducking.

Chen nhac vao roi de nguyen mot muc la cach lam hong tieng noi: nhac se dam vao
dai phu am va giong nghe duc. O day nhac tu ha xuong moi khi co tieng noi
(sidechain compression) roi tu nang lai o khoang nghi, va bi cat bot dai giua
de nhuong cho giong.

    python3 scripts/mix_music.py giong.wav nhac.mp3 ra.wav [--gain -20] [--duck 12]
"""
import os
import sys
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import media


def _threshold_for(duck_db):
    """Doi do lui mong muon (dB) thanh tham so threshold cua sidechaincompress.

    Do thuc te tren tin hieu thu: threshold moi quyet dinh do lui, con ratio gan
    nhu khong anh huong (ratio 6 va 20 chi cach nhau 0.4 dB). Cac diem do duoc:
        threshold 0.003 -> lui 11.2 dB
        threshold 0.010 -> lui  7.8 dB
        threshold 0.030 -> lui  1.2 dB
    Noi suy tuyen tinh tren log10(threshold) giua hai diem dau.
    """
    import math
    duck_db = max(2.0, min(14.0, duck_db))
    # log10(thr) = -2.52 khi lui 11.2 dB; do doc ~ +0.153 moi dB lui it di
    log_thr = -2.52 + (11.2 - duck_db) * 0.153
    return max(0.0015, min(0.05, 10 ** log_thr))


def prepare_bed(music_path, out_path, target_dur, fade=1.5):
    """Cat hoac lap nhac cho du target_dur giay, kem fade dau/cuoi."""
    src_dur = media.duration_of(music_path)
    tmp = out_path + ".loop.wav"
    if src_dur < target_dur - 0.05:
        # Lap lai cho du dai. -stream_loop can so lan lap, khong phai tong thoi luong.
        loops = int(target_dur // src_dur) + 1
        media.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                   "-stream_loop", str(loops), "-i", music_path,
                   "-t", f"{target_dur:.3f}", "-ac", str(media.CH),
                   "-ar", str(media.SR), "-c:a", "pcm_s16le", tmp])
    else:
        media.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                   "-i", music_path, "-t", f"{target_dur:.3f}",
                   "-ac", str(media.CH), "-ar", str(media.SR),
                   "-c:a", "pcm_s16le", tmp])
    fo = max(target_dur - fade, 0.1)
    media.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
               "-i", tmp, "-af",
               f"afade=t=in:st=0:d={fade},afade=t=out:st={fo:.3f}:d={fade}",
               "-c:a", "pcm_s16le", out_path])
    os.remove(tmp)
    return out_path


def mix(voice_path, music_path, out_path, gain_db=-20.0, duck_db=12.0,
        hp=90, notch_hz=1800, notch_db=-3.0, fade=1.5, clip_dur=None):
    """Tron nhac duoi giong.

    gain_db  : muc nhac so voi giong khi khong ai noi
    duck_db  : nhac lui bao nhieu dB khi co tieng noi (2-14, xem _threshold_for)
    hp       : cat tram duoi nguong nay khoi nhac cho khoi u
    notch_hz : ha nhe dai giua cua nhac de nhuong cho phu am
    clip_dur : do dai THAT cua video. Track giong luon duoc pad dai hon video mot
               chut (bien an toan cho -shortest), nen neu neo fade-out theo do dai
               file giong thi phan cuoi cua fade bi cat mat va nhac dut ngang.
               Truyen do dai video vao day de fade ket thuc dung luc clip het.
    """
    dur = media.duration_of(voice_path)
    bed = prepare_bed(music_path, out_path + ".bed.wav", dur, fade)

    thr = _threshold_for(duck_db)
    chain = (
        f"[1:a]highpass=f={hp},"
        f"equalizer=f={notch_hz}:t=h:w=1600:g={notch_db},"
        f"volume={gain_db}dB[bed];"
        f"[0:a]asplit=2[v1][vsc];"
        f"[bed][vsc]sidechaincompress="
        f"threshold={thr:.5f}:ratio=20:attack=8:release=280[ducked];"
        f"[v1][ducked]amix=inputs=2:duration=first:normalize=0,"
        f"alimiter=limit=0.92[out]"
    )
    # Fade-out cuoi cung neo vao do dai video, ap len ban da tron
    end = clip_dur if clip_dur else dur
    fo = max(end - fade, 0.1)
    chain = chain.replace("alimiter=limit=0.92[out]",
                          f"afade=t=out:st={fo:.3f}:d={fade},alimiter=limit=0.92[out]")
    media.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
               "-i", voice_path, "-i", bed, "-filter_complex", chain,
               "-map", "[out]", "-ac", str(media.CH), "-ar", str(media.SR),
               "-c:a", "pcm_s16le", out_path])
    os.remove(bed)
    return out_path


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("voice"); ap.add_argument("music"); ap.add_argument("out")
    ap.add_argument("--gain", type=float, default=-20.0)
    ap.add_argument("--duck", type=float, default=12.0)
    ap.add_argument("--notch", type=float, default=-3.0)
    ap.add_argument("--clip-dur", type=float, default=None,
                    help="do dai that cua video, de neo fade-out")
    a = ap.parse_args()
    mix(a.voice, a.music, a.out, gain_db=a.gain, duck_db=a.duck, notch_db=a.notch,
        clip_dur=a.clip_dur)
    print(f"  ra: {media.duration_of(a.out):.2f}s, {media.mean_volume_db(a.out):.1f} dBFS")
