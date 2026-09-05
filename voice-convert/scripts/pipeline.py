#!/usr/bin/env python3
"""Doi giong noi trong video: nu Bac -> nu Nam, dung ElevenLabs.

Chay 2 nhanh song song cho moi clip:
  A. Voice changer (speech-to-speech) — timing khop 100%, doi am sac.
  B. Doc lai (speech-to-text -> doi tu vung Bac/Nam -> text-to-speech) — ra chat giong Nam that.

Cach dung:
    export ELEVENLABS_API_KEY=...
    python3 scripts/pipeline.py                    # xu ly moi clip trong input/
    python3 scripts/pipeline.py --mode sts         # chi nhanh A
    python3 scripts/pipeline.py --mode tts         # chi nhanh B
    python3 scripts/pipeline.py --keep-music yes   # ep giu nhac nen
"""
import os
import re
import sys
import json
import time
import shutil
import argparse
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import el_api
import media
import north_to_south

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VIDEO_EXT = {".mp4", ".mov", ".mkv", ".webm", ".m4v", ".avi"}


def log(msg, indent=0):
    print(("  " * indent) + msg, flush=True)


# ---------------------------------------------------------------- config

def load_config(path):
    with open(path, encoding="utf-8") as f:
        cfg = json.load(f)
    vid = (cfg.get("voice_id") or "").strip()
    if not vid or vid.startswith("<"):
        raise SystemExit(
            "config.json chua co voice_id thuc.\n"
            "Chay: python3 scripts/list_voices.py --add  de chon giong nu mien Nam tu Voice Library."
        )
    return cfg


# ---------------------------------------------------------------- segmentation

def _split_at_largest_gap(words, max_chars):
    """Chia mot chuoi tu thanh cac manh <= max_chars, cat tai khoang nghi dai nhat.

    Can thiet cho clip noi lien mach khong dau cau: cat cung theo so ky tu se
    ngat giua cau, TTS doc sai ngu dieu. Cat tai cho nguoi ta thuc su nghi hoi.
    """
    text = " ".join(w["text"] for w in words)
    if len(text) <= max_chars or len(words) < 2:
        return [words]

    # Chi xet cac diem cat de hai nua deu khong qua ngan
    lo, hi = max(1, len(words) // 5), min(len(words) - 1, len(words) * 4 // 5)
    if lo >= hi:
        lo, hi = 1, len(words)
    gaps = [(i, float(words[i]["start"]) - float(words[i - 1]["end"]))
            for i in range(lo, hi)]
    if not gaps:
        best_i = len(words) // 2
    else:
        best_gap = max(g for _, g in gaps)
        # Khi cac khoang nghi xap xi nhau (noi lien mach), chon diem gan giua nhat
        # de khong sinh ra manh vun 2-3 tu.
        mid = len(words) / 2
        best_i = min((i for i, g in gaps if g >= best_gap - 0.01),
                     key=lambda i: abs(i - mid))

    return (_split_at_largest_gap(words[:best_i], max_chars)
            + _split_at_largest_gap(words[best_i:], max_chars))


def group_words(stt, gap_threshold=0.55, max_chars=220):
    """Gom tung tu tu STT thanh cac cau co start/end de canh timing.

    Cat theo dau cau va khoang nghi truoc; cau nao van qua dai thi chia tiep
    tai khoang nghi dai nhat ben trong no.
    """
    words = [w for w in stt.get("words", []) if w.get("type") in (None, "word")]
    words = [{"text": (w.get("text") or "").strip(),
              "start": float(w.get("start", 0)), "end": float(w.get("end", 0))}
             for w in words if (w.get("text") or "").strip()]

    if not words:
        text = (stt.get("text") or "").strip()
        return [{"text": text, "start": 0.0, "end": 0.0}] if text else []

    # Vong 1: ngat theo dau cau / khoang nghi
    chunks, cur = [], []
    for i, w in enumerate(words):
        cur.append(w)
        nxt = words[i + 1] if i + 1 < len(words) else None
        gap = (nxt["start"] - w["end"]) if nxt else 999.0
        ends_sentence = bool(re.search(r"[.!?…]$", w["text"]))
        if nxt is None or ends_sentence or gap > gap_threshold:
            chunks.append(cur)
            cur = []
    if cur:
        chunks.append(cur)

    # Vong 2: cau con qua dai -> chia tai khoang nghi dai nhat
    segs = []
    for ch in chunks:
        for part in _split_at_largest_gap(ch, max_chars):
            segs.append({
                "text": " ".join(w["text"] for w in part),
                "start": part[0]["start"],
                "end": part[-1]["end"],
            })
    return segs


# ---------------------------------------------------------------- nhanh A: voice changer

def branch_sts(video, workdir, outdir, name, cfg, src_audio, bed, total_dur):
    log("Nhanh A — voice changer (speech-to-speech)", 1)
    raw = os.path.join(workdir, "A_sts_raw.mp3")
    el_api.speech_to_speech(
        src_audio, cfg["voice_id"], raw,
        model_id=cfg.get("sts_model_id", "eleven_multilingual_sts_v2"),
        voice_settings=cfg.get("sts_voice_settings"),
        remove_background_noise=bool(cfg.get("sts_remove_background_noise", False)),
    )
    log(f"doi am sac xong ({media.duration_of(raw):.2f}s)", 2)

    fitted = os.path.join(workdir, "A_fitted.wav")
    got, ratio, clamped = media.fit_to_duration(
        raw, fitted, total_dur,
        max_stretch=cfg.get("max_stretch", 1.40),
        min_stretch=cfg.get("min_stretch", 0.95),
    )
    if abs(ratio - 1.0) > 0.02:
        log(f"canh timing: ti le {ratio:.3f}{' (bi gioi han)' if clamped else ''}", 2)

    padded = os.path.join(workdir, "A_padded.wav")
    media.pad_to_duration(fitted, padded, total_dur)

    mixed = os.path.join(workdir, "A_mixed.wav")
    media.mix_tracks(padded, bed, mixed, bed_gain_db=cfg.get("bed_gain_db", -3.0))
    out = os.path.join(outdir, f"{name}__A-voicechanger.mp4")
    media.mux(video, mixed, out)
    log(f"-> {os.path.relpath(out, ROOT)}", 2)
    return {"output": out, "stretch_ratio": round(ratio, 4), "clamped": clamped}


# ---------------------------------------------------------------- nhanh B: doc lai

def branch_tts(video, workdir, outdir, name, cfg, vocals, bed, total_dur):
    log("Nhanh B — doc lai (STT -> doi tu vung -> TTS)", 1)

    stt = el_api.speech_to_text(
        vocals,
        model_id=cfg.get("stt_model_id", "scribe_v1"),
        language_code=cfg.get("language_code", "vi"),
        diarize=bool(cfg.get("diarize", True)),
    )
    with open(os.path.join(workdir, "B_stt.json"), "w", encoding="utf-8") as f:
        json.dump(stt, f, ensure_ascii=False, indent=2)

    segs = group_words(
        stt,
        gap_threshold=cfg.get("segment_gap_threshold", 0.55),
        max_chars=cfg.get("segment_max_chars", 220),
    )
    if not segs:
        raise RuntimeError("STT khong boc duoc chu nao — clip co giong noi khong?")
    log(f"boc duoc {len(segs)} cau", 2)

    rules, warn, protect = north_to_south.load_rules(
        muc_do=cfg.get("muc_do_doi_tu_vung", "nhe"))
    all_changes, all_warnings = [], []
    for s in segs:
        s["text_bac"] = s["text"]
        s["text_nam"], ch, wn = north_to_south.convert(
            s["text"], rules, warn, protect=protect)
        all_changes += ch
        all_warnings += wn

    uniq_ch = sorted({f"{a.lower()}→{b}" for a, b in all_changes})
    log(f"doi tu vung: {len(all_changes)} luot ({', '.join(uniq_ch[:12])}"
        f"{'…' if len(uniq_ch) > 12 else ''})", 2)
    if all_warnings:
        uniq_wn = sorted({f"{a}?→{b}" for a, b in all_warnings})
        log(f"! can anh duyet tay: {', '.join(uniq_wn)}", 2)

    # TTS tung cau, keo gian vao dung khung thoi gian cua cau goc
    pieces, cursor, drift, clamped_n = [], 0.0, 0.0, 0
    for i, s in enumerate(segs):
        slot = max(s["end"] - s["start"], 0.25)
        gap = s["start"] - cursor
        if gap > 0.02:
            sil = os.path.join(workdir, f"B_sil_{i:03d}.wav")
            pieces.append(media.silence_wav(gap, sil))
            cursor += gap

        mp3 = os.path.join(workdir, f"B_seg_{i:03d}.mp3")
        el_api.text_to_speech(
            s["text_nam"], cfg["voice_id"], mp3,
            model_id=cfg.get("tts_model_id", "eleven_multilingual_v2"),
            voice_settings=cfg.get("tts_voice_settings"),
            previous_text=segs[i - 1]["text_nam"] if i > 0 else None,
            next_text=segs[i + 1]["text_nam"] if i + 1 < len(segs) else None,
        )
        wav = os.path.join(workdir, f"B_seg_{i:03d}.wav")
        got, ratio, was_clamped = media.fit_to_duration(
            mp3, wav, slot,
            max_stretch=cfg.get("max_stretch", 1.40),
            min_stretch=cfg.get("min_stretch", 0.95),
        )
        if got > slot + 0.02:
            clamped_n += 1
            drift += got - slot
        pieces.append(wav)
        cursor += got
        s.update(slot=round(slot, 3), tts_dur=round(got, 3), ratio=round(ratio, 3))
        if (i + 1) % 5 == 0 or i + 1 == len(segs):
            log(f"TTS {i + 1}/{len(segs)}", 3)

    if clamped_n:
        log(f"! {clamped_n} cau khong nhet vua khung, lech tich luy {drift:+.2f}s", 2)

    raw_voice = media.concat_wavs(pieces, os.path.join(workdir, "B_voice.wav"))
    voice = os.path.join(workdir, "B_voice_padded.wav")
    media.pad_to_duration(raw_voice, voice, total_dur)

    mixed = os.path.join(workdir, "B_mixed.wav")
    media.mix_tracks(voice, bed, mixed, bed_gain_db=cfg.get("bed_gain_db", -3.0))
    out = os.path.join(outdir, f"{name}__B-doclai.mp4")
    media.mux(video, mixed, out)
    log(f"-> {os.path.relpath(out, ROOT)}", 2)

    return {
        "output": out,
        "segments": segs,
        "vocab_changes": uniq_ch,
        "needs_review": sorted({f"{a}?→{b}" for a, b in all_warnings}),
        "clamped_segments": clamped_n,
        "drift_sec": round(drift, 3),
    }


# ---------------------------------------------------------------- 1 clip

def process(video, outdir, workroot, cfg, mode, keep_music):
    name = os.path.splitext(os.path.basename(video))[0]
    workdir = os.path.join(workroot, name)
    os.makedirs(workdir, exist_ok=True)
    log(f"\n=== {os.path.basename(video)} ===")

    info = media.probe(video)
    if not info["has_audio"]:
        raise RuntimeError("clip khong co track audio")
    total = info["duration"]
    log(f"thoi luong {total:.2f}s", 1)

    original = media.extract_audio(video, os.path.join(workdir, "original.mp3"))

    # Tach giong khoi nhac nen (ElevenLabs audio-isolation)
    vocals = os.path.join(workdir, "vocals.mp3")
    el_api.isolate_voice(original, vocals)
    log("tach giong khoi nen xong", 1)

    if keep_music == "auto":
        has_music, stats = media.has_background_music(
            original, vocals, threshold_db=cfg.get("music_detect_threshold_db", 12.0)
        )
        log(f"do nhac nen: goc {stats['orig_db']}dB / nen {stats['bed_db']}dB "
            f"(cach {stats['gap_db']}dB) -> {'CO nhac nen, se giu' if has_music else 'khong dang ke, bo'}", 1)
    else:
        has_music = keep_music == "yes"
        stats = {"forced": keep_music}
        log(f"nhac nen: {'giu' if has_music else 'bo'} (anh chi dinh)", 1)

    bed = None
    if has_music:
        bed = media.residual_bed(original, vocals, os.path.join(workdir, "bed.wav"))

    report = {
        "clip": os.path.basename(video),
        "duration": round(total, 3),
        "keep_music": has_music,
        "music_stats": stats,
        "voice_id": cfg["voice_id"],
    }

    if mode in ("both", "sts"):
        report["A_voicechanger"] = branch_sts(
            video, workdir, outdir, name, cfg,
            vocals if has_music else original, bed, total
        )
    if mode in ("both", "tts"):
        report["B_doclai"] = branch_tts(
            video, workdir, outdir, name, cfg, vocals, bed, total
        )

    rp = os.path.join(outdir, f"{name}__report.json")
    with open(rp, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    return report


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description="Doi giong nu Bac -> nu Nam trong video")
    ap.add_argument("--input", default=os.path.join(ROOT, "input"))
    ap.add_argument("--output", default=os.path.join(ROOT, "output"))
    ap.add_argument("--work", default=os.path.join(ROOT, "work"))
    ap.add_argument("--config", default=os.path.join(ROOT, "config.json"))
    ap.add_argument("--mode", choices=["both", "sts", "tts"], default=None,
                    help="both = xuat ca 2 ban de so (mac dinh trong config)")
    ap.add_argument("--keep-music", choices=["auto", "yes", "no"], default=None,
                    help="auto = tu do nhac nen roi quyet dinh")
    ap.add_argument("--clean-work", action="store_true", help="xoa work/ truoc khi chay")
    args = ap.parse_args()

    media.require_ffmpeg()
    cfg = load_config(args.config)
    mode = args.mode or cfg.get("mode", "both")
    keep_music = args.keep_music or cfg.get("keep_music", "auto")

    if args.clean_work and os.path.isdir(args.work):
        shutil.rmtree(args.work)
    os.makedirs(args.output, exist_ok=True)
    os.makedirs(args.work, exist_ok=True)

    vids = sorted(
        os.path.join(args.input, f) for f in os.listdir(args.input)
        if os.path.splitext(f)[1].lower() in VIDEO_EXT
    ) if os.path.isdir(args.input) else []

    if not vids:
        log(f"Khong thay clip nao trong {args.input}/")
        log(f"Bo file .mp4 / .mov vao do roi chay lai. Duoi ho tro: {', '.join(sorted(VIDEO_EXT))}")
        return 0

    log(f"Tim thay {len(vids)} clip | mode={mode} | nhac nen={keep_music} | voice={cfg['voice_id']}")

    ok, failed = [], []
    t0 = time.time()
    for v in vids:
        try:
            process(v, args.output, args.work, cfg, mode, keep_music)
            ok.append(os.path.basename(v))
        except Exception as e:
            failed.append((os.path.basename(v), str(e)))
            log(f"!! LOI o {os.path.basename(v)}: {e}", 1)
            traceback.print_exc(file=sys.stderr)

    log(f"\n=== Xong sau {time.time() - t0:.0f}s: {len(ok)} thanh cong, {len(failed)} loi ===")
    for f, e in failed:
        log(f"loi: {f} — {e}", 1)
    log(f"Clip ket qua nam trong: {args.output}/")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
