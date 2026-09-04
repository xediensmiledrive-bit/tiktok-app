#!/usr/bin/env python3
"""Doi giong hang loat: nu mien Bac -> nu mien Nam, kem nhac nen.

Chay dung chuoi da duoc duyet tren clip mau, KHONG phai chuoi cu trong
pipeline.py. Khac biet chinh: doc ca bai roi canh nhip bang khoang nghi (thay vi
doc tung cau), can tong theo giong goc, tron nhac co ducking, va chan dinh bang
cach do tren ban da encode.

Chay hai pha de khoi dot credit oan:

    python3 scripts/batch.py --pha 1     # boc chu + chuyen tu vung, ~24% chi phi
    (doc lai file *.nam.txt trong work/, sua neu can)
    python3 scripts/batch.py --pha 2     # doc + ghep, ~76% chi phi

Hoac chay thang ca hai:
    python3 scripts/batch.py --pha ca-hai

Bo qua clip da xong nen dut giua chung chay lai duoc.
"""
import os
import re
import sys
import json
import time
import argparse
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import el_api
import media
import north_to_south
import fit_by_pauses
import match_tone
import mix_music
import safe_peak

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VIDEO_EXT = {".mp4", ".mov", ".mkv", ".webm", ".m4v", ".avi"}


def log(m, i=0):
    print("  " * i + m, flush=True)


def clips_in(d):
    if not os.path.isdir(d):
        return []
    return sorted(os.path.join(d, f) for f in os.listdir(d)
                  if os.path.splitext(f)[1].lower() in VIDEO_EXT)


# ---------------------------------------------------------------- pha 1

def pha1(video, wd, cfg):
    """Boc chu va chuyen tu vung. Ghi ra file de nguoi duyet truoc khi doc."""
    name = os.path.basename(video)
    stt_path = os.path.join(wd, "stt.json")
    bac_path = os.path.join(wd, "bac.txt")
    nam_path = os.path.join(wd, "nam.txt")

    if os.path.exists(nam_path):
        log("da boc chu tu truoc, bo qua", 1)
        return json.load(open(stt_path, encoding="utf-8"))

    a16 = os.path.join(wd, "stt_input.mp3")
    media.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
               "-i", video, "-vn", "-ac", "1", "-ar", "16000",
               "-c:a", "libmp3lame", "-b:a", "64k", a16])

    stt = el_api.speech_to_text(a16,
                                model_id=cfg.get("stt_model_id", "scribe_v1"),
                                language_code=cfg.get("language_code", "vi"),
                                diarize=False)
    json.dump(stt, open(stt_path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

    bac = (stt.get("text") or "").strip()
    open(bac_path, "w", encoding="utf-8").write(bac + "\n")

    rules, warn, protect = north_to_south.load_rules(
        muc_do=cfg.get("muc_do_doi_tu_vung", "nhe"))
    nam, changes, warnings = north_to_south.convert(bac, rules, warn, protect=protect)
    open(nam_path, "w", encoding="utf-8").write(nam + "\n")

    uniq = sorted({f"{a.lower()}→{b}" for a, b in changes})
    log(f"boc {len(bac)} ky tu | doi {len(changes)} luot: "
        f"{', '.join(uniq[:8])}{'…' if len(uniq) > 8 else ''}", 1)
    if warnings:
        log(f"! can duyet tay: {', '.join(sorted({a for a, _ in warnings}))}", 1)
    return stt


# ---------------------------------------------------------------- pha 2

def pha2(video, wd, outdir, cfg, total_dur):
    """Doc lai bang giong da chot, canh nhip, can tong, tron nhac, ghep."""
    name = os.path.splitext(os.path.basename(video))[0]
    nam_path = os.path.join(wd, "nam.txt")
    if not os.path.exists(nam_path):
        raise RuntimeError("chua co nam.txt — chay pha 1 truoc")
    text = open(nam_path, encoding="utf-8").read().strip()
    if not text:
        raise RuntimeError("nam.txt rong")

    # Am thanh goc chat luong day du, dung lam moc can tong
    ref = os.path.join(wd, "goc_full.wav")
    if not os.path.exists(ref):
        media.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                   "-i", video, "-vn", "-ac", "2", "-ar", "44100",
                   "-c:a", "pcm_s16le", ref])

    # 1. Doc ca bai
    raw = os.path.join(wd, "tts.mp3")
    if not os.path.exists(raw):
        el_api.text_to_speech(text, cfg["voice_id"], raw,
                              model_id=cfg.get("tts_model_id", "eleven_v3"),
                              voice_settings=cfg.get("tts_voice_settings"))
    log(f"doc xong: {media.duration_of(raw):.2f}s (khung {total_dur:.2f}s)", 1)

    # 2. Canh nhip bang khoang nghi
    fitted = os.path.join(wd, "fit.wav")
    info = fit_by_pauses.fit(raw, fitted, total_dur, workdir=wd)
    log(f"canh nhip: {info.get('cach')} | " +
        " ".join(f"{k}={v}" for k, v in info.items() if k != "cach"), 1)

    # 3. Nen dong luc TRUOC roi moi can tong (nen sau se xo lai can bang tan so)
    comp = os.path.join(wd, "comp.wav")
    media.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
               "-i", fitted, "-af",
               "acompressor=threshold=-24dB:ratio=4:attack=5:release=120:makeup=6",
               "-ac", "2", "-ar", "44100", "-c:a", "pcm_s16le", comp])

    # 4. Can tong theo giong goc cua clip
    eq = os.path.join(wd, "eq.wav")
    match_tone.match(comp, ref, eq, verbose=False)
    pm, pg = match_tone.profile(eq), match_tone.profile(ref)
    lech = (sum((x - y) ** 2 for x, y in zip(pm, pg)) / len(pm)) ** 0.5
    log(f"can tong: lech {lech:.2f} dB so voi giong goc", 1)

    # 5. Chuan hoa, chua headroom cho AAC
    master = os.path.join(wd, "master.wav")
    media.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
               "-i", eq, "-af",
               "loudnorm=I=-12:TP=-3.0:LRA=3,alimiter=limit=0.80",
               "-ac", "2", "-ar", "44100", "-c:a", "pcm_s16le", master])
    voice = os.path.join(wd, "voice.wav")
    media.pad_to_duration(master, voice, total_dur)

    # 6. Nhac nen
    nn = cfg.get("nhac_nen") or {}
    nhac = nn.get("file")
    if nhac:
        nhac_path = nhac if os.path.isabs(nhac) else os.path.join(ROOT, nhac)
        if not os.path.exists(nhac_path):
            raise RuntimeError(f"khong thay file nhac: {nhac_path}")
        final_audio = os.path.join(wd, "voice_music.wav")
        mix_music.mix(voice, nhac_path, final_audio,
                      gain_db=nn.get("gain_db", -2.0),
                      duck_db=nn.get("duck_db", 10.0),
                      notch_db=nn.get("notch_db", -3.0),
                      fade=nn.get("fade_giay", 1.5),
                      clip_dur=total_dur)
    else:
        final_audio = voice
        log("khong chen nhac nen (config de trong)", 1)

    # 7. Ghep, chan dinh do tren ban da encode
    out = os.path.join(outdir, f"{name}__Nam.mp4")
    peak = safe_peak.render(video, final_audio, out, target_tp=-1.0)
    log(f"chan dinh: bu {peak['gain_db']:+.2f} dB -> {peak['tp']:+.2f} dBTP", 1)
    return out, {"lech_tong_db": round(lech, 2), "canh_nhip": info, "dinh": peak}


# ---------------------------------------------------------------- kiem tra

def kiem_tra(src, out):
    """Cac phep kiem da dung suot phien: khung hinh, hinh nguyen ban, dinh."""
    import subprocess
    def frames(f):
        return subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_packets",
             "-show_entries", "stream=nb_read_packets", "-of", "csv=p=0", f],
            capture_output=True, text=True).stdout.strip()
    def vmd5(f):
        return subprocess.run(
            ["ffmpeg", "-v", "error", "-i", f, "-map", "0:v", "-c", "copy",
             "-f", "md5", "-"], capture_output=True, text=True).stdout.strip()
    a, b = media.probe(src), media.probe(out)
    r = {
        "du_khung_hinh": frames(src) == frames(out),
        "hinh_nguyen_ban": vmd5(src) == vmd5(out),
        "thoi_luong_khop": abs(a["duration"] - b["duration"]) < 0.35,
        "dinh_khong_clip": safe_peak.true_peak(out) < -0.3,
    }
    r["tat_ca_dat"] = all(r.values())
    return r


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description="Doi giong hang loat")
    ap.add_argument("--input", default=os.path.join(ROOT, "input"))
    ap.add_argument("--output", default=os.path.join(ROOT, "output"))
    ap.add_argument("--work", default=os.path.join(ROOT, "work"))
    ap.add_argument("--config", default=os.path.join(ROOT, "config.json"))
    ap.add_argument("--pha", choices=["1", "2", "ca-hai"], default="ca-hai")
    ap.add_argument("--lam-lai", action="store_true", help="lam lai ca clip da xong")
    args = ap.parse_args()

    media.require_ffmpeg()
    cfg = json.load(open(args.config, encoding="utf-8"))
    vid = (cfg.get("voice_id") or "").strip()
    if not vid or vid.startswith("<"):
        raise SystemExit("config.json chua chon voice_id")

    os.makedirs(args.output, exist_ok=True)
    os.makedirs(args.work, exist_ok=True)
    vids = clips_in(args.input)
    if not vids:
        log(f"Khong thay clip nao trong {args.input}/")
        return 0

    tong_kytu = 0
    log(f"{len(vids)} clip | pha {args.pha} | giong {cfg.get('voice_name') or vid} "
        f"| model {cfg.get('tts_model_id')}")
    xong, loi = [], []
    t0 = time.time()

    for i, v in enumerate(vids, 1):
        name = os.path.splitext(os.path.basename(v))[0]
        wd = os.path.join(args.work, name)
        os.makedirs(wd, exist_ok=True)
        out = os.path.join(args.output, f"{name}__Nam.mp4")
        log(f"\n[{i}/{len(vids)}] {os.path.basename(v)}")

        if os.path.exists(out) and not args.lam_lai:
            log("da co ban ra, bo qua (dung --lam-lai de lam lai)", 1)
            xong.append(name)
            continue
        try:
            info = media.probe(v)
            if not info["has_audio"]:
                raise RuntimeError("clip khong co track audio")
            log(f"{info['duration']:.2f}s", 1)

            if args.pha in ("1", "ca-hai"):
                pha1(v, wd, cfg)
                tong_kytu += len(open(os.path.join(wd, "nam.txt"), encoding="utf-8").read().strip())
            if args.pha == "1":
                xong.append(name)
                continue

            outfile, rep = pha2(v, wd, args.output, cfg, info["duration"])
            kt = kiem_tra(v, outfile)
            rep["kiem_tra"] = kt
            json.dump(rep, open(os.path.join(args.output, f"{name}__bao-cao.json"),
                                "w", encoding="utf-8"), ensure_ascii=False, indent=2)
            if kt["tat_ca_dat"]:
                log("kiem tra: tat ca dat", 1)
            else:
                fail = [k for k, ok in kt.items() if k != "tat_ca_dat" and not ok]
                log(f"! kiem tra KHONG dat: {', '.join(fail)}", 1)
            xong.append(name)
        except Exception as e:
            loi.append((os.path.basename(v), str(e)))
            log(f"!! LOI: {e}", 1)
            traceback.print_exc(file=sys.stderr)

    log(f"\n=== Xong sau {time.time() - t0:.0f}s: {len(xong)} thanh cong, {len(loi)} loi ===")
    for f, e in loi:
        log(f"loi: {f} — {e}", 1)
    if args.pha == "1":
        log(f"\nTong van ban: {tong_kytu} ky tu (~{tong_kytu} credit khi doc o pha 2)")
        log(f"Doc lai cac file nam.txt trong {args.work}/, sua neu can, roi chay --pha 2")
    else:
        log(f"Clip ket qua: {args.output}/")
    return 1 if loi else 0


if __name__ == "__main__":
    sys.exit(main())
