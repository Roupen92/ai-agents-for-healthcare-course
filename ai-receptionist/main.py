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
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Form, Request
from fastapi.responses import FileResponse, PlainTextResponse

load_dotenv()

from brain import EMERGENCY_RESPONSE, generate_response, is_emergency  # noqa: E402
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


def _base_url() -> str:
    return os.environ.get("PUBLIC_BASE_URL", "http://localhost:8000").rstrip("/")


def _save_audio(call_sid: str, text: str) -> str:
    """Synthesizes `text`, saves it, returns the public URL Twilio can fetch."""
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
    _conversations[CallSid] = []
    audio_url = _save_audio(CallSid, GREETING)
    return PlainTextResponse(
        _twiml_gather_and_play(audio_url, NO_INPUT), media_type="application/xml"
    )


@app.post("/respond")
async def respond(CallSid: str = Form(...), SpeechResult: str = Form("")):
    history = _conversations.setdefault(CallSid, [])

    if not SpeechResult.strip():
        audio_url = _save_audio(CallSid, NO_INPUT)
        return PlainTextResponse(
            _twiml_play_and_hangup(audio_url), media_type="application/xml"
        )

    if is_emergency(SpeechResult):
        audio_url = _save_audio(CallSid, EMERGENCY_RESPONSE)
        return PlainTextResponse(
            _twiml_play_and_hangup(audio_url), media_type="application/xml"
        )

    reply = generate_response(SpeechResult, history)
    history.append({"role": "user", "content": SpeechResult})
    history.append({"role": "assistant", "content": reply})

    audio_url = _save_audio(CallSid, reply)
    return PlainTextResponse(
        _twiml_gather_and_play(audio_url, GOODBYE), media_type="application/xml"
    )


@app.get("/audio/{filename}")
async def audio(filename: str):
    return FileResponse(AUDIO_DIR / filename, media_type="audio/mpeg")


@app.get("/health")
async def health():
    return {"status": "ok"}
