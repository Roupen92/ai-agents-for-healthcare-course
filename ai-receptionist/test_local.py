"""
Local end-to-end verification that doesn't need a real phone call.

Run: source .venv/bin/activate && python test_local.py

Covers everything that can be checked without Twilio: the emergency
keyword gate, the LLM staying in scope, real ElevenLabs audio generation,
and the full FastAPI request/response cycle Twilio would actually drive.
"""

import re
import xml.etree.ElementTree as ET

from dotenv import load_dotenv

load_dotenv()

from fastapi.testclient import TestClient  # noqa: E402

from brain import is_emergency, generate_response  # noqa: E402
from voice import synthesize_speech  # noqa: E402
from main import app, _conversations  # noqa: E402

PASS = "PASS"
FAIL = "FAIL"


def check(label, condition, detail=""):
    status = PASS if condition else FAIL
    print(f"[{status}] {label}" + (f" — {detail}" if detail else ""))
    return condition


def main():
    results = []

    # 1. Emergency keyword gate, pure logic, no API calls.
    print("\n--- emergency keyword gate ---")
    results.append(check(
        "catches chest pain", is_emergency("I have really bad chest pain")))
    results.append(check(
        "catches suicidal ideation", is_emergency("I want to kill myself")))
    results.append(check(
        "does not flag routine scheduling",
        not is_emergency("I'd like to reschedule my appointment for Friday")))
    results.append(check(
        "does not flag insurance question",
        not is_emergency("Do you take Blue Cross insurance?")))

    # 2. The LLM actually answers in-scope questions and stays short.
    print("\n--- in-scope LLM response ---")
    reply = generate_response(
        "Hi, I'd like to reschedule my appointment to next Tuesday.", [])
    print(f"  caller: I'd like to reschedule my appointment to next Tuesday.")
    print(f"  assistant: {reply}")
    results.append(check(
        "reply is short enough for a phone call", len(reply) < 400,
        f"{len(reply)} chars"))

    # 3. The LLM refuses to give medical advice and redirects instead.
    print("\n--- scope refusal on a clinical question ---")
    reply2 = generate_response(
        "My knee has been hurting for a week, what should I take for it?", [])
    print(f"  caller: My knee has been hurting for a week, what should I take for it?")
    print(f"  assistant: {reply2}")
    no_advice_markers = ["ibuprofen", "take", "medication", "recommend"]
    gave_advice = any(m in reply2.lower() for m in ["you should take", "i recommend"])
    results.append(check(
        "did not directly prescribe/recommend a medication",
        not gave_advice))
    offered_callback = any(w in reply2.lower() for w in ["nurse", "call you back", "call back"])
    results.append(check(
        "offered a callback instead of medical advice", offered_callback))

    # 4. Real ElevenLabs call produces real audio.
    print("\n--- ElevenLabs synthesis ---")
    audio_bytes = synthesize_speech("Thanks for calling, how can I help you today?")
    results.append(check(
        "got non-trivial audio back", len(audio_bytes) > 5000,
        f"{len(audio_bytes)} bytes"))
    results.append(check(
        "looks like an mp3", audio_bytes[:3] == b"ID3" or audio_bytes[:2] == b"\xff\xfb",
        f"first bytes: {audio_bytes[:4]!r}"))

    # 5. Full FastAPI cycle for a normal call: /voice -> /respond -> /audio
    print("\n--- full webhook cycle: normal call ---")
    client = TestClient(app)
    call_sid = "CA_test_normal_001"

    r1 = client.post("/voice", data={"CallSid": call_sid})
    results.append(check("/voice returns 200", r1.status_code == 200))
    results.append(check("/voice returns XML", "application/xml" in r1.headers.get("content-type", "")))
    root1 = ET.fromstring(r1.text)
    gather1 = root1.find("Gather")
    results.append(check("/voice TwiML has <Gather>", gather1 is not None))
    play1 = gather1.find("Play") if gather1 is not None else None
    results.append(check("/voice TwiML has <Play> inside Gather", play1 is not None))

    if play1 is not None:
        audio_url = play1.text.strip()
        audio_path = re.sub(r"^https?://[^/]+", "", audio_url)
        r_audio = client.get(audio_path)
        results.append(check(
            "the exact URL Twilio would fetch actually serves audio",
            r_audio.status_code == 200 and len(r_audio.content) > 1000,
            f"status={r_audio.status_code} bytes={len(r_audio.content)}"))

    r2 = client.post("/respond", data={
        "CallSid": call_sid,
        "SpeechResult": "I need to reschedule my appointment to next week",
    })
    root2 = ET.fromstring(r2.text)
    results.append(check(
        "/respond (normal) continues the call with another <Gather>",
        root2.find("Gather") is not None))
    results.append(check(
        "conversation history recorded for this call",
        len(_conversations.get(call_sid, [])) == 2))

    # 6. Full cycle for an emergency: must hang up, must never hit the LLM.
    print("\n--- full webhook cycle: emergency call ---")
    call_sid_2 = "CA_test_emergency_001"
    client.post("/voice", data={"CallSid": call_sid_2})
    r3 = client.post("/respond", data={
        "CallSid": call_sid_2,
        "SpeechResult": "I'm having really bad chest pain and I can't breathe",
    })
    root3 = ET.fromstring(r3.text)
    results.append(check(
        "emergency call ends with <Hangup/>, not another <Gather>",
        root3.find("Hangup") is not None and root3.find("Gather") is None))
    results.append(check(
        "emergency call never reached the LLM (no history recorded)",
        len(_conversations.get(call_sid_2, [])) == 0))

    print(f"\n{sum(results)}/{len(results)} checks passed")
    if not all(results):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
