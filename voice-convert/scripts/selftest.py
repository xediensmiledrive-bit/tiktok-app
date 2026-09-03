#!/usr/bin/env python3
"""Self-test cho pipeline, KHONG can mang va KHONG ton credit ElevenLabs.

Tao 1 clip test (giong + nhac nen), mock cac endpoint ElevenLabs, chay tron
pipeline, roi kiem:
  - clip ket qua dai dung bang clip goc (khong bi -shortest cat cut hinh)
  - phat hien duoc nhac nen
  - gom cau theo timestamp dung
  - doi tu vung Bac -> Nam dung
  - khong cau nao bi keo nhao (ti le >= min_stretch)

    python3 scripts/selftest.py
"""
import os
import sys
import json
import shutil
import tempfile
import subprocess

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

import el_api
import media
import pipeline
import north_to_south

# Cau goc gia lap, kem timestamp tung tu (nhu Scribe tra ve)
FAKE_WORDS = [
    ("Bố", 0.5, 0.8), ("mẹ", 0.8, 1.1), ("tớ", 1.1, 1.4), ("bảo", 1.4, 1.8),
    ("thế", 1.8, 2.2), ("nào", 2.2, 2.6), ("cũng", 2.6, 2.9), ("được.", 2.9, 3.2),
    ("Đắt", 4.0, 4.4), ("lắm", 4.4, 4.8), ("đấy", 4.8, 5.2), ("nhé,", 5.2, 5.6),
    ("ông", 5.6, 6.0), ("ấy", 6.0, 6.3), ("nói", 6.3, 6.7), ("vậy.", 6.7, 7.1),
    ("Mua", 8.0, 8.4), ("hai", 8.4, 8.8), ("quả", 8.8, 9.2), ("dứa", 9.2, 9.7),
    ("với", 9.7, 10.1), ("một", 10.1, 10.5), ("bát", 10.5, 10.9), ("ngô.", 10.9, 11.2),
]
DURATION = 12.0

results = []


def check(label, cond, detail=""):
    results.append((label, bool(cond)))
    print(f"{'[OK] ' if cond else '[LOI]'} {label}" + (f" — {detail}" if detail else ""))
    return cond


def ff(args):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error"] + args, check=True)


def build_fixtures(d):
    """Clip 12s: hinh mau, audio = giong 200Hz + nhac nen 800Hz (-8dB)."""
    clip = os.path.join(d, "input", "test-bac.mp4")
    ff(["-f", "lavfi", "-i", f"testsrc=size=320x240:rate=25:duration={DURATION}",
        "-f", "lavfi", "-i", f"sine=frequency=200:duration={DURATION}",
        "-f", "lavfi", "-i", f"sine=frequency=800:duration={DURATION}",
        "-filter_complex", "[1:a]volume=0dB[v];[2:a]volume=-8dB[m];"
                           "[v][m]amix=inputs=2:normalize=0[a]",
        "-map", "0:v", "-map", "[a]", "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-shortest", clip])
    vocals = os.path.join(d, "vocals_pure.mp3")
    ff(["-f", "lavfi", "-i", f"sine=frequency=200:duration={DURATION}",
        "-c:a", "libmp3lame", vocals])
    return clip, vocals


def install_mocks(vocals_src):
    """Thay cac endpoint ElevenLabs bang ban gia lap."""
    def isolate(audio_path, out_path):
        shutil.copy(vocals_src, out_path)
        return out_path

    def stt(audio_path, **kw):
        return {"language_code": "vi",
                "text": " ".join(w[0] for w in FAKE_WORDS),
                "words": [{"text": t, "start": s, "end": e, "type": "word"}
                          for t, s, e in FAKE_WORDS]}

    def tts(text, voice_id, out_path, **kw):
        # ~0.075s/ky tu: co cau dai hon khung, co cau ngan hon
        ff(["-f", "lavfi", "-i", f"sine=frequency=330:duration={max(0.4, len(text) * 0.075):.3f}",
            "-c:a", "libmp3lame", out_path])
        return out_path

    def sts(audio_path, voice_id, out_path, **kw):
        ff(["-i", audio_path, "-c:a", "libmp3lame", out_path])
        return out_path

    for name, fn in (("isolate_voice", isolate), ("speech_to_text", stt),
                     ("text_to_speech", tts), ("speech_to_speech", sts)):
        setattr(el_api, name, fn)
        setattr(pipeline.el_api, name, fn)


def main():
    media.require_ffmpeg()
    print("=== Self-test pipeline doi giong (mock ElevenLabs) ===\n")

    # -- Tu dien Bac -> Nam --
    out, changes, _ = north_to_south.convert(
        "Bố mẹ tớ bảo thế nào cũng được, đắt lắm đấy nhé."
    )
    check("tu dien Bac->Nam", out == "Ba má tui bảo sao cũng được, mắc quá đó nha.", out)
    check("giu kieu hoa dau cau", out.startswith("Ba má"), out[:12])

    d = tempfile.mkdtemp(prefix="voiceconv-selftest-")
    try:
        for sub in ("input", "output", "work"):
            os.makedirs(os.path.join(d, sub), exist_ok=True)
        clip, vocals = build_fixtures(d)
        install_mocks(vocals)

        cfg = json.load(open(os.path.join(ROOT, "config.json"), encoding="utf-8"))
        cfg["voice_id"] = "SELFTEST_MOCK_VOICE"

        cwd = os.getcwd()
        os.chdir(d)
        try:
            rep = pipeline.process(clip, os.path.join(d, "output"),
                                   os.path.join(d, "work"), cfg, "both", "auto")
        finally:
            os.chdir(cwd)

        src = media.probe(clip)["duration"]
        print()
        for key, label in (("A_voicechanger", "A (voice changer)"),
                           ("B_doclai", "B (doc lai)")):
            info = media.probe(rep[key]["output"])
            check(f"nhanh {label}: dai dung bang clip goc",
                  abs(info["duration"] - src) < 0.35,
                  f"{info['duration']:.2f}s vs {src:.2f}s")
            check(f"nhanh {label}: con ca hinh va tieng",
                  info["has_audio"] and info["has_video"])

        check("phat hien nhac nen", rep["keep_music"] is True,
              f"cach {rep['music_stats'].get('gap_db')}dB")

        segs = rep["B_doclai"]["segments"]
        check("gom cau theo timestamp", len(segs) == 3, f"{len(segs)} cau")
        floor = cfg.get("min_stretch", 0.95)
        check("khong cau nao bi keo nhao",
              all(s["ratio"] >= floor - 1e-6 for s in segs),
              f"ti le: {[s['ratio'] for s in segs]}")
        check("moi cau khop khung thoi gian",
              all(s["tts_dur"] <= s["slot"] + 0.05 for s in segs),
              f"lech tich luy {rep['B_doclai']['drift_sec']}s")
        check("co ghi log doi tu vung", len(rep["B_doclai"]["vocab_changes"]) >= 10,
              f"{len(rep['B_doclai']['vocab_changes'])} cap tu")
    finally:
        shutil.rmtree(d, ignore_errors=True)

    passed = sum(1 for _, ok in results if ok)
    print(f"\n=== {passed}/{len(results)} pass ===")
    if passed != len(results):
        print("That bai: " + ", ".join(l for l, ok in results if not ok))
        return 1
    print("Pipeline san sang. Chi con can ELEVENLABS_API_KEY + voice_id de chay that.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
