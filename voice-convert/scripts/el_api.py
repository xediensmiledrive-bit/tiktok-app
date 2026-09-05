"""Thin client cho cac endpoint ElevenLabs ma pipeline nay dung.

Key doc tu bien moi truong ELEVENLABS_API_KEY. Khong hardcode key vao file.
"""
import os
import sys
import time
import json
import requests

BASE = os.environ.get("ELEVENLABS_BASE_URL", "https://api.elevenlabs.io")
TIMEOUT = (15, 600)  # (connect, read) - TTS/STT dai nen read timeout lon


class ElevenLabsError(RuntimeError):
    pass


def _load_dotenv():
    """Nap voice-convert/.env neu bien moi truong chua co key.

    File .env nam trong .gitignore va de quyen 600 — key khong bao gio vao git.
    """
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def _key():
    k = os.environ.get("ELEVENLABS_API_KEY", "").strip()
    if not k:
        _load_dotenv()
        k = os.environ.get("ELEVENLABS_API_KEY", "").strip()
    if not k:
        raise ElevenLabsError(
            "Chua co ELEVENLABS_API_KEY. Dat vao voice-convert/.env "
            "(dong: ELEVENLABS_API_KEY=...) hoac export bien moi truong."
        )
    return k


def _headers(extra=None):
    h = {"xi-api-key": _key()}
    if extra:
        h.update(extra)
    return h


def _request(method, path, *, retries=3, **kw):
    """Goi API co retry cho loi mang / 429 / 5xx."""
    url = BASE + path
    delay = 2
    last = None
    for attempt in range(retries + 1):
        try:
            r = requests.request(method, url, timeout=TIMEOUT, **kw)
        except requests.RequestException as e:
            last = f"loi mang: {e}"
        else:
            if r.status_code < 400:
                return r
            body = r.text[:500]
            last = f"HTTP {r.status_code}: {body}"
            # 4xx (tru 429) la loi cua minh -> khong retry
            if r.status_code != 429 and r.status_code < 500:
                raise ElevenLabsError(f"{method} {path} -> {last}")
        if attempt < retries:
            print(f"  ! {last} — thu lai sau {delay}s", file=sys.stderr)
            time.sleep(delay)
            delay *= 2
    raise ElevenLabsError(f"{method} {path} that bai sau {retries + 1} lan: {last}")


# ---------------------------------------------------------------- voices

def list_my_voices():
    """Voice trong tai khoan."""
    r = _request("GET", "/v1/voices", headers=_headers())
    return r.json().get("voices", [])


def search_shared_voices(language="vi", gender=None, page_size=100):
    """Tim voice trong Voice Library cong dong."""
    params = {"page_size": page_size}
    if language:
        params["language"] = language
    if gender:
        params["gender"] = gender
    r = _request("GET", "/v1/shared-voices", headers=_headers(), params=params)
    return r.json().get("voices", [])


def add_shared_voice(public_owner_id, voice_id, name):
    """Them voice tu Library vao tai khoan de dung duoc voice_id."""
    r = _request(
        "POST",
        f"/v1/voices/add/{public_owner_id}/{voice_id}",
        headers=_headers({"Content-Type": "application/json"}),
        json={"new_name": name},
    )
    return r.json().get("voice_id")


# ---------------------------------------------------------------- speech to text

def speech_to_text(audio_path, model_id="scribe_v1", language_code="vi", diarize=True):
    """Boc chu kem timestamp tung tu."""
    with open(audio_path, "rb") as f:
        data = {
            "model_id": model_id,
            "timestamps_granularity": "word",
            "diarize": "true" if diarize else "false",
        }
        if language_code:
            data["language_code"] = language_code
        r = _request(
            "POST",
            "/v1/speech-to-text",
            headers=_headers(),
            files={"file": (os.path.basename(audio_path), f, "audio/mpeg")},
            data=data,
        )
    return r.json()


# ---------------------------------------------------------------- text to speech

def text_to_speech(text, voice_id, out_path, model_id="eleven_multilingual_v2",
                   voice_settings=None, output_format="mp3_44100_128",
                   previous_text=None, next_text=None):
    """Doc text thanh audio. previous_text/next_text giup giu ngu dieu lien mach."""
    payload = {"text": text, "model_id": model_id}
    if voice_settings:
        payload["voice_settings"] = voice_settings
    if previous_text:
        payload["previous_text"] = previous_text
    if next_text:
        payload["next_text"] = next_text
    r = _request(
        "POST",
        f"/v1/text-to-speech/{voice_id}",
        headers=_headers({"Content-Type": "application/json"}),
        params={"output_format": output_format},
        json=payload,
    )
    with open(out_path, "wb") as f:
        f.write(r.content)
    return out_path


# ---------------------------------------------------------------- speech to speech

def speech_to_speech(audio_path, voice_id, out_path,
                     model_id="eleven_multilingual_sts_v2",
                     voice_settings=None, output_format="mp3_44100_128",
                     remove_background_noise=False):
    """Voice changer: giu nguyen nhip noi / cam xuc, chi doi am sac."""
    with open(audio_path, "rb") as f:
        data = {
            "model_id": model_id,
            "remove_background_noise": "true" if remove_background_noise else "false",
        }
        if voice_settings:
            data["voice_settings"] = json.dumps(voice_settings)
        r = _request(
            "POST",
            f"/v1/speech-to-speech/{voice_id}",
            headers=_headers(),
            params={"output_format": output_format},
            files={"audio": (os.path.basename(audio_path), f, "audio/mpeg")},
            data=data,
        )
    with open(out_path, "wb") as f:
        f.write(r.content)
    return out_path


# ---------------------------------------------------------------- audio isolation

def isolate_voice(audio_path, out_path):
    """Tach giong noi ra khoi nhac nen / tieng on."""
    with open(audio_path, "rb") as f:
        r = _request(
            "POST",
            "/v1/audio-isolation",
            headers=_headers(),
            files={"audio": (os.path.basename(audio_path), f, "audio/mpeg")},
        )
    with open(out_path, "wb") as f:
        f.write(r.content)
    return out_path
