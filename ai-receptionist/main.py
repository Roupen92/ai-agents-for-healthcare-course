"""
AI clinic receptionist — Twilio answers the call, this app decides what to
say, ElevenLabs speaks it.

Call flow:
  1. Twilio hits POST /voice when a call comes in. We greet the caller and
     <Gather> their spoken reply (Twilio's own speech-to-text).
  2. Twilio hits POST /respond with the transcript. We check it for an
     emergency first (see brain.is_emergency), then either give the fixed
     911 message or ask the LLM (brain.generate_response) what to say.
  3. Either way we synthesize the reply with ElevenLabs, save it, and tell
     Twilio to <Play> it, then <Gather> again to continue the call.
  4. GET /audio/{call_sid}/{n}.mp3 is how Twilio actually fetches that
     audio — it needs a public URL to play, it can't take raw bytes.

Nothing here is wired to a real clinic's real schedule. The LLM is scoped
to scheduling/hours/insurance/message-taking only, and never handles
anything that looks like a real medical emergency — see brain.py.
"""

import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Form, Request
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

load_dotenv()

from brain import EMERGENCY_RESPONSE, generate_response, is_emergency  # noqa: E402
from scheduler import extract_appointment  # noqa: E402
from tracing import trace, traced_step  # noqa: E402
from voice import synthesize_speech  # noqa: E402

app = FastAPI()

AUDIO_DIR = Path(__file__).parent / "audio_cache"
AUDIO_DIR.mkdir(exist_ok=True)

GREETING = (
    "Thanks for calling. I'm the clinic's AI assistant. "
    "How can I help you today?"
)
NO_INPUT = "Sorry, I didn't catch anything. Goodbye."
GOODBYE = "Thanks for calling. Goodbye."

# call_sid -> list of {"role": ..., "content": ...}, oldest first.
# In-memory only: fine for a demo/single-process dev server, NOT for
# production, where this needs to live in Redis or a database so it
# survives a restart and works across multiple server processes.
_conversations: dict[str, list[dict]] = {}

# call_sid -> {"status": "active"|"completed"|"emergency"|"no_input",
#              "started_at": iso str}. Powers the dashboard's call list.
_calls: dict[str, dict] = {}

# call_sid -> the extracted appointment dict from scheduler.py, re-checked
# and overwritten after every turn so it stays current as the call goes on.
_appointments: dict[str, dict] = {}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _refresh_appointment(call_sid: str) -> None:
    history = _conversations.get(call_sid, [])
    result = extract_appointment(history)
    if result:
        _appointments[call_sid] = {**result, "call_sid": call_sid, "updated_at": _now()}


def _base_url() -> str:
    return os.environ.get("PUBLIC_BASE_URL", "http://localhost:8000").rstrip("/")


def _save_audio(call_sid: str, text: str) -> str:
    """Synthesizes `text`, saves it, returns the public URL Twilio can fetch."""
    with traced_step(call_sid, "tts"):
        audio_bytes = synthesize_speech(text)
    filename = f"{call_sid}-{uuid.uuid4().hex[:8]}.mp3"
    (AUDIO_DIR / filename).write_bytes(audio_bytes)
    return f"{_base_url()}/audio/{filename}"


def _twiml_gather_and_play(audio_url: str, fallback_text: str) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Gather input="speech" action="/respond" method="POST" speechTimeout="auto" language="en-US">
    <Play>{audio_url}</Play>
  </Gather>
  <Say>{fallback_text}</Say>
</Response>"""


def _twiml_play_and_hangup(audio_url: str) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Play>{audio_url}</Play>
  <Hangup/>
</Response>"""


@app.post("/voice")
async def voice(CallSid: str = Form(...)):
    trace(CallSid, "call_started")
    _conversations[CallSid] = []
    _calls[CallSid] = {"status": "active", "started_at": _now()}
    audio_url = _save_audio(CallSid, GREETING)
    return PlainTextResponse(
        _twiml_gather_and_play(audio_url, NO_INPUT), media_type="application/xml"
    )


@app.post("/respond")
async def respond(CallSid: str = Form(...), SpeechResult: str = Form("")):
    history = _conversations.setdefault(CallSid, [])
    call = _calls.setdefault(CallSid, {"status": "active", "started_at": _now()})

    # Length only, never the words themselves. A trace tells you THAT a
    # caller said something and roughly how much, never WHAT.
    trace(CallSid, "speech_received", chars=len(SpeechResult.strip()))

    if not SpeechResult.strip():
        call["status"] = "no_input"
        trace(CallSid, "call_ended", reason="no_input")
        audio_url = _save_audio(CallSid, NO_INPUT)
        return PlainTextResponse(
            _twiml_play_and_hangup(audio_url), media_type="application/xml"
        )

    emergency = is_emergency(SpeechResult)
    trace(CallSid, "emergency_check", triggered=emergency)
    if emergency:
        call["status"] = "emergency"
        trace(CallSid, "call_ended", reason="emergency")
        audio_url = _save_audio(CallSid, EMERGENCY_RESPONSE)
        return PlainTextResponse(
            _twiml_play_and_hangup(audio_url), media_type="application/xml"
        )

    with traced_step(CallSid, "llm_response"):
        reply = generate_response(SpeechResult, history)
    history.append({"role": "user", "content": SpeechResult})
    history.append({"role": "assistant", "content": reply})
    call["status"] = "active"

    with traced_step(CallSid, "appointment_extraction"):
        _refresh_appointment(CallSid)

    audio_url = _save_audio(CallSid, reply)
    trace(CallSid, "turn_complete", turns=len(history) // 2)
    return PlainTextResponse(
        _twiml_gather_and_play(audio_url, GOODBYE), media_type="application/xml"
    )


@app.get("/audio/{filename}")
async def audio(filename: str):
    return FileResponse(AUDIO_DIR / filename, media_type="audio/mpeg")


@app.get("/health")
async def health():
    return {"status": "ok"}


# ---------------------------------------------------------------------
# Dashboard API — read-only JSON the frontend polls. Nothing here takes
# input from a caller directly, so it doesn't need the same scrutiny as
# the call-handling endpoints above, but it's still PHI if a real call
# ever touches it. See the HIPAA section of the course README.
# ---------------------------------------------------------------------


@app.get("/api/stats")
async def api_stats():
    statuses = [c["status"] for c in _calls.values()]
    return {
        "total_calls": len(_calls),
        "emergency_calls": statuses.count("emergency"),
        "active_calls": statuses.count("active"),
        "appointments_captured": len(_appointments),
    }


@app.get("/api/calls")
async def api_calls():
    out = []
    for call_sid, call in sorted(
        _calls.items(), key=lambda kv: kv[1]["started_at"], reverse=True
    ):
        history = _conversations.get(call_sid, [])
        last = history[-1]["content"] if history else ""
        out.append({
            "call_sid": call_sid,
            "status": call["status"],
            "started_at": call["started_at"],
            "turns": len(history),
            "preview": last[:80],
        })
    return out


@app.get("/api/calls/{call_sid}/transcript")
async def api_transcript(call_sid: str):
    return {
        "call_sid": call_sid,
        "status": _calls.get(call_sid, {}).get("status", "unknown"),
        "messages": _conversations.get(call_sid, []),
    }


@app.get("/api/appointments")
async def api_appointments():
    return sorted(
        _appointments.values(), key=lambda a: a["updated_at"], reverse=True
    )


static_dir = Path(__file__).parent / "static"
static_dir.mkdir(exist_ok=True)
app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")
