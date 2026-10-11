"""Pulls a structured appointment request out of a conversation, if there
is one. Separate small LLM call, kept apart from brain.py's reply logic
so the two prompts can't bleed into each other."""

import json
import os

from openai import OpenAI

EXTRACT_PROMPT = """You are reading a transcript between an AI clinic \
receptionist and a caller. Decide if the caller asked to schedule, \
reschedule, or cancel an appointment, or asked for a callback (for a \
refill or a clinical question).

If yes, return JSON with exactly these keys:
{"intent": "schedule" | "reschedule" | "cancel" | "callback",
 "caller_name": string or null,
 "callback_number": string or null,
 "requested_time": string or null,
 "reason": string or null}

If the conversation is NOT about any of those (just hours, insurance,
location, small talk), return exactly: {"intent": null}

Only use information actually present in the transcript. Never invent a
name, number, or time that wasn't said. Return JSON only, nothing else.
"""


def extract_appointment(history: list[dict]) -> dict | None:
    if not history:
        return None
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    transcript = "\n".join(f"{m['role']}: {m['content']}" for m in history)
    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": EXTRACT_PROMPT},
            {"role": "user", "content": transcript},
        ],
        response_format={"type": "json_object"},
        max_tokens=200,
        temperature=0,
    )
    data = json.loads(resp.choices[0].message.content)
    if not data.get("intent"):
        return None
    return data
