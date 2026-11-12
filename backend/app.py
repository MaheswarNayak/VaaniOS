"""
VaaniOS Backend API
Flask application handling business transactions, health checks, daily summaries,
and Gnani AI voice intelligence (Prisma Speech-to-Text & Timbre Text-to-Speech).
"""

import base64
import io
import os
import shutil
import subprocess
from typing import Any, Dict
import uuid
from flask import Flask, Response, jsonify, request
from flask_cors import CORS

import agent
import database
import gnani_client
from database import (
    get_latest_transactions,
    get_summary_today,
    get_summary_weekly,
    init_db,
    insert_transaction,
    undo_last_transaction,
)

# Initialize Flask application
app = Flask(__name__)

# Enable Cross-Origin Resource Sharing (CORS) for all routes
CORS(app, resources={r"/api/*": {"origins": "*"}})

# Ensure database and tables are created upon startup
init_db()

# Global in-memory storage for pending voice actions awaiting confirmation
PENDING_ACTIONS: Dict[str, Any] = {}


def transcode_audio_to_wav(audio_bytes: bytes, target_sr: int = 16000) -> bytes:
    """
    Transcode incoming audio bytes (WebM, M4A, OGG, MP3, etc.) from MediaRecorder
    into standard 16-bit PCM WAV (16kHz, mono) for Gnani Prisma STT.

    Workflow:
      1. Uses pydub (with io.BytesIO) if ffprobe is detected in system PATH.
      2. Uses imageio-ffmpeg or system ffmpeg for in-memory stdin->stdout pipe conversion.
      3. Passes through valid WAV if already in RIFF format.
    """
    if not audio_bytes:
        raise ValueError("Audio bytes cannot be empty.")

    # 1. Try pydub with io.BytesIO if ffprobe/avprobe is available on PATH
    if shutil.which("ffprobe") or shutil.which("avprobe"):
        try:
            from pydub import AudioSegment
            seg = AudioSegment.from_file(io.BytesIO(audio_bytes))
            seg = seg.set_frame_rate(target_sr).set_channels(1).set_sample_width(2)
            out_buf = io.BytesIO()
            seg.export(out_buf, format="wav")
            return out_buf.getvalue()
        except Exception:
            pass

    # 2. In-memory FFmpeg stream conversion via imageio-ffmpeg or system ffmpeg
    ffmpeg_exe = None
    try:
        import imageio_ffmpeg
        ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        ffmpeg_exe = shutil.which("ffmpeg")

    if ffmpeg_exe:
        try:
            cmd = [
                ffmpeg_exe,
                "-y",
                "-i", "pipe:0",
                "-vn",
                "-acodec", "pcm_s16le",
                "-ar", str(target_sr),
                "-ac", "1",
                "-f", "wav",
                "pipe:1"
            ]
            proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            stdout, stderr = proc.communicate(input=audio_bytes)
            if proc.returncode == 0 and stdout:
                return stdout
            err_msg = stderr.decode("utf-8", errors="ignore")
            raise RuntimeError(f"FFmpeg conversion error: {err_msg}")
        except Exception as e:
            raise ValueError(f"Audio transcoding failed: {str(e)}")

    # 3. Fallback: if already a WAV file
    if audio_bytes.startswith(b"RIFF") and b"WAVE" in audio_bytes[:16]:
        return audio_bytes

    raise ValueError("No audio converter found. Please run: pip install imageio-ffmpeg")


# -----------------------------------------------------------------------------
# Core API Endpoints
# -----------------------------------------------------------------------------

@app.route("/api/health", methods=["GET"])
def health_check():
    """
    Health check endpoint.
    Returns:
        JSON response with status 'ok'.
    """
    return jsonify({"status": "ok"}), 200


@app.route("/api/transactions", methods=["POST"])
def create_transaction():
    """
    Accepts JSON payload:
        - type (str, required): Strictly 'sale' or 'expense'
        - amount (int, required): Strictly positive integer (> 0)
        - description (str, optional): Transaction note/description

    Validates inputs, saves transaction to SQLite, and returns the saved record.
    """
    payload = request.get_json(silent=True)
    if not payload or not isinstance(payload, dict):
        return jsonify({
            "error": "Invalid JSON",
            "message": "Request body must be a valid JSON object."
        }), 400

    trans_type = payload.get("type")
    amount = payload.get("amount")
    description = payload.get("description")

    # Validate 'type'
    if not trans_type or not isinstance(trans_type, str):
        return jsonify({
            "error": "Validation Error",
            "message": "Field 'type' is required and must be a string."
        }), 400

    normalized_type = trans_type.strip().lower()
    if normalized_type not in ("sale", "expense"):
        return jsonify({
            "error": "Validation Error",
            "message": "Field 'type' must be strictly 'sale' or 'expense'."
        }), 400

    # Validate 'amount'
    if amount is None or isinstance(amount, bool) or not isinstance(amount, int) or amount <= 0:
        return jsonify({
            "error": "Validation Error",
            "message": "Field 'amount' is required and must be a positive integer greater than 0."
        }), 400

    # Clean optional description
    clean_description = description.strip() if isinstance(description, str) else None

    # Insert into database
    try:
        saved_record = insert_transaction(
            trans_type=normalized_type,
            amount=amount,
            description=clean_description
        )
    except Exception as e:
        return jsonify({
            "error": "Database Error",
            "message": str(e)
        }), 500

    return jsonify(saved_record), 201


@app.route("/api/transactions", methods=["GET"])
def list_transactions():
    """
    Fetches and returns the latest 20 transactions from the database.
    Optionally accepts a `?date=YYYY-MM-DD` query parameter to filter by date.
    """
    try:
        target_date = request.args.get("date")
        if target_date:
            target_date = target_date.strip()
        transactions = get_latest_transactions(limit=20, target_date=target_date)
        return jsonify({
            "transactions": transactions,
            "count": len(transactions)
        }), 200
    except Exception as e:
        return jsonify({
            "error": "Database Error",
            "message": str(e)
        }), 500


@app.route("/api/summary/today", methods=["GET"])
def summary_today():
    """
    Calculates and returns total sum of 'sales' and total sum of 'expenses' for today
    or for an optional `?date=YYYY-MM-DD` query parameter.
    """
    try:
        target_date = request.args.get("date")
        if target_date:
            target_date = target_date.strip()
        summary = get_summary_today(target_date=target_date)
        return jsonify({
            "sales": summary["sales"],
            "expenses": summary["expenses"],
            "net_balance": summary["net_balance"]
        }), 200
    except Exception as e:
        return jsonify({
            "error": "Database Error",
            "message": str(e)
        }), 500


@app.route("/api/summary/weekly", methods=["GET"])
def summary_weekly():
    """
    Calculates and returns total sales and expenses grouped by day for the last 7 days
    in a JSON format suitable for Chart.js.
    """
    try:
        weekly = get_summary_weekly()
        return jsonify(weekly), 200
    except Exception as e:
        return jsonify({
            "error": "Database Error",
            "message": str(e)
        }), 500


@app.route("/api/transaction/undo", methods=["POST"])
def undo_transaction():
    """
    Deletes the most recently inserted transaction, recalculates today's summary,
    and returns the updated summary.
    """
    try:
        deleted = undo_last_transaction()
        if not deleted:
            return jsonify({
                "success": False,
                "error": "Not Found",
                "message": "No transaction found to undo."
            }), 404

        updated_summary = get_summary_today()
        return jsonify({
            "success": True,
            "message": "Last transaction undone.",
            "deleted_transaction": deleted,
            "updated_summary": updated_summary
        }), 200
    except Exception as e:
        return jsonify({
            "error": "Database Error",
            "message": str(e)
        }), 500


# -----------------------------------------------------------------------------
# Gnani AI Voice Pipeline Endpoints (Prisma STT & Timbre TTS)
# -----------------------------------------------------------------------------

@app.route("/api/voice/command", methods=["POST"])
@app.route("/api/voice/process-command", methods=["POST"])
def voice_command():
    """
    Unified Voice Command Endpoint:
    Accepts:
      1. Multipart form-data with 'audio_file' (WebM, M4A, WAV from MediaRecorder or microphone)
      2. JSON payload with {"transcript": "..."} (direct text testing or client transcription)

    Workflow:
      1. Ingest audio file (WebM / M4A / WAV).
      2. Transcode in-memory to 16-bit PCM WAV (16kHz mono).
      3. Transcribe audio via Gnani AI Prisma STT.
      4. Parse Hinglish intent and amount with agent.parse_voice_command.
      5. If unambiguous and auto_commit=true, execute transaction(s) via database.py.
      6. Synthesize spoken response in natural Hinglish via Gnani AI Timbre TTS.
      7. Return diagnostic response with transcript, parsed actions, updated summary, and base64 audio.
    """
    transcript = None
    auto_commit = True

    # 1. Check for audio file upload in multipart/form-data
    if "audio_file" in request.files or "audio" in request.files or "file" in request.files:
        audio_file = request.files.get("audio_file") or request.files.get("audio") or request.files.get("file")
        if not audio_file or audio_file.filename == "":
            return jsonify({
                "error": "Invalid Audio File",
                "message": "Uploaded file is empty or missing filename."
            }), 400

        raw_audio_bytes = audio_file.read()
        if len(raw_audio_bytes) == 0:
            return jsonify({
                "error": "Empty Audio File",
                "message": "The uploaded audio file contains 0 bytes."
            }), 400

        # Transcode incoming audio (WebM/M4A/etc.) to standard 16-bit PCM WAV
        try:
            wav_bytes = transcode_audio_to_wav(raw_audio_bytes, target_sr=16000)
        except Exception as e:
            return jsonify({
                "error": "Audio Transcoding Failed",
                "message": f"Could not transcode audio to standard WAV: {str(e)}"
            }), 400

        language_code = request.form.get("language_code", "en-IN")
        raw_auto_commit = request.form.get("auto_commit", "true")
        auto_commit = str(raw_auto_commit).strip().lower() in ("true", "1", "yes")

        # Transcribe standard WAV with Gnani Prisma
        stt_result = gnani_client.transcribe_audio(
            audio_bytes=wav_bytes,
            filename="command.wav",
            language_code=language_code,
            use_itn=True
        )

        if not stt_result.get("success"):
            return jsonify({
                "error": "Transcription Failed",
                "details": stt_result.get("error")
            }), 502

        transcript = stt_result.get("transcript", "").strip()

    # 2. Check for direct JSON payload
    elif request.is_json or request.content_type == "application/json":
        payload = request.get_json(silent=True) or {}
        transcript = payload.get("transcript")
        raw_auto = payload.get("auto_commit", payload.get("execute_immediately", True))
        if isinstance(raw_auto, str):
            auto_commit = raw_auto.strip().lower() in ("true", "1", "yes")
        else:
            auto_commit = bool(raw_auto)

    # 3. Check for form field 'transcript'
    elif "transcript" in request.form:
        transcript = request.form.get("transcript")
        raw_auto = request.form.get("auto_commit", "true")
        auto_commit = str(raw_auto).strip().lower() in ("true", "1", "yes")

    else:
        return jsonify({
            "error": "Unsupported Request Format",
            "message": "Please send a multipart upload with 'audio_file' or a JSON object with 'transcript'."
        }), 400

    if transcript is None:
        return jsonify({
            "error": "Missing Transcript",
            "message": "Transcript could not be extracted from the request."
        }), 400

    # Process command through agent
    result = agent.process_voice_action(
        transcript=transcript,
        auto_commit=auto_commit
    )

    parsed = result.get("parsed", {})
    if not auto_commit and parsed.get("intent") in ("add_sale", "add_expense", "multi_action"):
        parsed["requires_confirmation"] = True
        result["requires_confirmation"] = True

    # When requires_confirmation is True, generate unique action_id and save pending actions
    requires_conf = bool(parsed.get("requires_confirmation") or result.get("requires_confirmation"))
    if requires_conf:
        parsed["requires_confirmation"] = True
        result["requires_confirmation"] = True

        if "actions" not in parsed:
            if parsed.get("type") and parsed.get("amount"):
                parsed["actions"] = [{
                    "type": parsed["type"],
                    "amount": parsed["amount"],
                    "description": parsed.get("description", parsed["type"])
                }]
            else:
                parsed["actions"] = []

        action_id = str(uuid.uuid4())
        PENDING_ACTIONS[action_id] = parsed["actions"]
        result["action_id"] = action_id
        parsed["action_id"] = action_id
    else:
        result["action_id"] = None

    if "extracted_data" not in result:
        if parsed.get("actions") and len(parsed["actions"]) > 0:
            result["extracted_data"] = parsed["actions"][0]
        elif parsed.get("type") or parsed.get("amount"):
            result["extracted_data"] = {
                "type": parsed.get("type"),
                "amount": parsed.get("amount"),
                "description": parsed.get("description")
            }

    # Flag whether transactions were successfully processed and saved to SQLite
    # Required by frontend app.js to trigger automatic dashboard refresh
    is_saved = bool(
        result.get("transaction_saved", False) or (
            result.get("success") and
            result.get("executed") and
            result.get("parsed", {}).get("intent") in ("add_sale", "add_expense", "multi_action")
        )
    )
    result["transaction_saved"] = is_saved
    result["reply_text"] = result.get("response_text")
    if "intent" not in result:
        result["intent"] = result.get("parsed", {}).get("intent")

    return jsonify(result), 200


@app.route("/api/voice/confirm", methods=["POST"])
def voice_confirm():
    """
    Accepts JSON payload:
      - action_id (str, required): The ID of the pending action to confirm or cancel.
      - confirmed (bool, optional): True to confirm and commit to DB, False to cancel. Default True.

    If confirmed is True:
      - Pops the action from PENDING_ACTIONS.
      - Saves each action to SQLite via database.py.
      - Recalculates today's summary.
      - Returns JSON with transaction_saved=True and a success message.
    If confirmed is False:
      - Pops and discards the pending action.
      - Returns JSON indicating cancellation.
    """
    payload = request.get_json(silent=True)
    if not payload or not isinstance(payload, dict):
        return jsonify({
            "error": "Invalid JSON",
            "message": "Request body must be a valid JSON object."
        }), 400

    action_id = payload.get("action_id")
    if not action_id or not isinstance(action_id, str):
        return jsonify({
            "error": "Validation Error",
            "message": "Field 'action_id' is required and must be a string."
        }), 400

    if action_id not in PENDING_ACTIONS:
        return jsonify({
            "error": "Not Found",
            "message": f"Action ID '{action_id}' not found or already processed."
        }), 404

    raw_confirmed = payload.get("confirmed", True)
    if isinstance(raw_confirmed, str):
        confirmed = raw_confirmed.strip().lower() in ("true", "1", "yes")
    else:
        confirmed = bool(raw_confirmed)

    action_data = PENDING_ACTIONS.pop(action_id, None)

    if not confirmed:
        summary = get_summary_today()
        return jsonify({
            "success": True,
            "transaction_saved": False,
            "message": "Action cancelled.",
            "updated_summary": summary
        }), 200

    if isinstance(action_data, list):
        for act in action_data:
            if isinstance(act, dict) and act.get("type") and act.get("amount"):
                insert_transaction(
                    trans_type=act["type"],
                    amount=int(act["amount"]),
                    description=act.get("description")
                )
    elif isinstance(action_data, dict):
        if action_data.get("type") and action_data.get("amount"):
            insert_transaction(
                trans_type=action_data["type"],
                amount=int(action_data["amount"]),
                description=action_data.get("description")
            )

    get_summary_today()

    return jsonify({
        "success": True,
        "transaction_saved": True,
        "message": "Transaction successfully saved."
    }), 200


@app.route("/api/speech", methods=["POST"])
def synthesize_speech():
    """
    Synthesize arbitrary backend text into spoken voice via Gnani AI Timbre TTS.
    Accepts JSON:
      - text (str, required): Text to speak.
      - voice (str, optional): Voice name (default 'Poorvi').
      - language (str, optional): Language code (default 'hi-en' for Hinglish).
      - format (str, optional): 'wav' (binary stream) or 'base64' (JSON string).
    """
    payload = request.get_json(silent=True) or {}
    text = payload.get("text") or request.form.get("text")
    if not text or not str(text).strip():
        return jsonify({
            "error": "Validation Error",
            "message": "Field 'text' is required and cannot be empty."
        }), 400

    voice = payload.get("voice", request.form.get("voice", "Poorvi"))
    language = payload.get("language", request.form.get("language", "hi-en"))
    model = payload.get("model", request.form.get("model", "timbre-v2.5"))
    speed = float(payload.get("speed", request.form.get("speed", 1.0)))
    req_format = payload.get("format", request.args.get("format", "wav")).lower()

    tts_result = gnani_client.synthesize_speech(
        text=str(text).strip(),
        voice=voice,
        model=model,
        language=language,
        speed=speed
    )

    if not tts_result.get("success") or not tts_result.get("audio_bytes"):
        return jsonify({
            "error": "TTS Synthesis Failed",
            "details": tts_result.get("error")
        }), 502

    if req_format == "base64":
        audio_b64 = base64.b64encode(tts_result["audio_bytes"]).decode("utf-8")
        return jsonify({
            "success": True,
            "audio_base64": audio_b64,
            "content_type": tts_result.get("content_type", "audio/wav")
        }), 200

    return Response(
        tts_result["audio_bytes"],
        mimetype=tts_result.get("content_type", "audio/wav"),
        headers={
            "Content-Disposition": 'inline; filename="synthesized_speech.wav"',
            "Content-Length": str(len(tts_result["audio_bytes"]))
        }
    )


if __name__ == "__main__":
    # Run development server
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
