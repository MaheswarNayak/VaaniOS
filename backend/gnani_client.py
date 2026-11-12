"""
gnani_client.py - VaaniOS Adapter for Gnani AI Voice Models
===========================================================
Handles Speech-to-Text (Prisma REST API) and Text-to-Speech (Timbre REST API).
"""

import os
import requests
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

STT_URL = "https://api.vachana.ai/stt/v3"
TTS_URL = "https://api.vachana.ai/api/v1/tts/inference"


def get_api_key() -> str:
    """Retrieve and validate the Gnani API key from environment variables."""
    api_key = os.getenv("GNANI_API_KEY")
    if not api_key or api_key.strip() == "":
        raise ValueError("GNANI_API_KEY is missing! Please set it in backend/.env")
    return api_key.strip()


def transcribe_audio(
    audio_bytes: bytes,
    filename: str = "command.wav",
    language_code: str = "hi-IN",
    use_itn: bool = True
) -> dict:
    """
    Send audio to Gnani Prisma (STT REST API) and return normalized result.
    - language_code='en-IN' accepts English-Hindi mixed (Hinglish) audio and outputs Latin script.
    - language_code='hi-IN' outputs Devanagari script.
    - format='transcribe' enables ITN (converts spoken numbers to digits like ₹500).
    """
    try:
        api_key = get_api_key()
    except ValueError as e:
        return {"success": False, "transcript": "", "error": str(e)}

    headers = {
        "X-API-Key-ID": api_key
    }

    # Prepare multipart/form-data payload
    files = {
        "audio_file": (filename, audio_bytes, "audio/wav")
    }
    data = {
        "language_code": language_code,
        "format": "transcribe" if use_itn else "verbatim",
        "itn_native_numerals": "false",
        " bias_lists": '["sale", "expense", "rupaye", "maal", "kharcha", "summary"]',
        "bias_score": "1.0"
    }

    try:
        response = requests.post(
            STT_URL,
            headers=headers,
            files=files,
            data=data,
            timeout=20
        )
        if response.status_code == 200:
            res_json = response.json()
            return {
                "success": True,
                "transcript": res_json.get("transcript", "").strip(),
                "request_id": res_json.get("request_id"),
                "raw": res_json
            }
        else:
            return {
                "success": False,
                "transcript": "",
                "status_code": response.status_code,
                "error": f"Prisma STT Error ({response.status_code}): {response.text}"
            }
    except requests.exceptions.RequestException as e:
        return {
            "success": False,
            "transcript": "",
            "error": f"Network error calling Prisma STT: {str(e)}"
        }


def synthesize_speech(
    text: str,
    voice: str = "Poorvi",
    model: str = "timbre-v2.5",
    language: str = "hi-en",
    speed: float = 1.0,
    sample_rate: int = 24000
) -> dict:
    """
    Send response text to Gnani Timbre (TTS REST API) and return WAV binary audio.
    - Default voice 'Poorvi' with 'hi-en' is tuned for Hinglish.
    - Or use voice='Nalini' with language='hi-IN' for Hindi.
    """
    if not text or not text.strip():
        return {"success": False, "audio_bytes": None, "error": "Text cannot be empty"}

    try:
        api_key = get_api_key()
    except ValueError as e:
        return {"success": False, "audio_bytes": None, "error": str(e)}

    headers = {
        "Content-Type": "application/json",
        "X-API-Key-ID": api_key
    }

    payload = {
        "text": text.strip(),
        "voice": voice,
        "model": model,
        "language": language,
        "speed": speed,
        "audio_config": {
            "sample_rate": sample_rate,
            "num_channels": 1,
            "sample_width": 2,
            "encoding": "linear_pcm",
            "container": "wav"
        }
    }

    try:
        response = requests.post(
            TTS_URL,
            headers=headers,
            json=payload,
            timeout=20
        )
        if response.status_code == 200:
            return {
                "success": True,
                "audio_bytes": response.content,
                "content_type": response.headers.get("Content-Type", "audio/wav")
            }
        else:
            return {
                "success": False,
                "audio_bytes": None,
                "status_code": response.status_code,
                "error": f"Timbre TTS Error ({response.status_code}): {response.text}"
            }
    except requests.exceptions.RequestException as e:
        return {
            "success": False,
            "audio_bytes": None,
            "error": f"Network error calling Timbre TTS: {str(e)}"
        }


# =====================================================================
# Quick Self-Test: Run `python3 gnani_client.py` to test both APIs!
# =====================================================================
if __name__ == "__main__":
    print("1. Testing Timbre TTS (Text-to-Speech)...")
    test_phrase = "Namaste, aaj pachees sau rupaye ki sale record ho gayi hai."
    tts_result = synthesize_speech(
        text=test_phrase,
        voice="Poorvi",
        model="timbre-v2.5",
        language="hi-en"
    )

    if tts_result["success"]:
        sample_wav = "test_vaani_sample.wav"
        with open(sample_wav, "wb") as f:
            f.write(tts_result["audio_bytes"])
        print(f"   ✅ TTS Success! Saved {len(tts_result['audio_bytes'])} bytes to '{sample_wav}'.")

        print("\n2. Testing Prisma STT (Speech-to-Text) using the generated WAV file...")
        stt_result = transcribe_audio(
            audio_bytes=tts_result["audio_bytes"],
            filename=sample_wav,
            language_code="en-IN",
            use_itn=True
        )
        if stt_result["success"]:
            print(f"   ✅ STT Success (en-IN / Hinglish)! Transcript: \"{stt_result['transcript']}\"")
        else:
            print(f"   ❌ STT Failed: {stt_result['error']}")
    else:
        print(f"   ❌ TTS Failed: {tts_result['error']}")