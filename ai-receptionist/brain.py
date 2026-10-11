"""
The "brain": turns what a caller said into what the receptionist says back.

Scope is deliberately narrow and enforced in code, not just in the prompt:
this assistant handles scheduling, hours, location, insurance, and message
-taking. It never gives medical advice, triages symptoms, or discusses a
diagnosis. Anything that sounds like a real emergency is caught by
is_emergency() BEFORE the LLM ever sees it, and gets a fixed, hard-coded
response that always tells the caller to hang up and call 911. That check
is not optional and should never be routed through the model.
"""

import os

from openai import OpenAI

EMERGENCY_KEYWORDS = [
    "chest pain", "can't breathe", "cant breathe", "cannot breathe",
    "difficulty breathing", "trouble breathing", "not breathing",
    "severe bleeding", "heavy bleeding", "bleeding a lot", "won't stop bleeding",
    "suicide", "suicidal", "kill myself", "want to die", "end my life",
    "overdose", "unconscious", "unresponsive", "passed out",
    "stroke", "face drooping", "numb on one side", "numbness on one side",
    "seizure", "convulsing",
    "allergic reaction", "anaphylaxis", "throat closing",
    "choking",
    "heart attack",
]

EMERGENCY_RESPONSE = (
    "It sounds like this may be a medical emergency. Please hang up right now "
    "and dial 911, or go to your nearest emergency room. If you are able to, "
    "stay on the line with emergency services until help arrives."
)

SYSTEM_PROMPT = """You are the front-desk phone assistant for a medical clinic. \
Your ONLY job is: scheduling and rescheduling appointments, telling callers \
the clinic's hours and location, telling them what insurance the clinic \
accepts, and taking a message for a prescription refill or a question for \
a nurse to call back about.

Hard rules, never break these:
- Never give medical advice. Never discuss symptoms, diagnoses, medications, \
dosing, or what a caller "should do" about how they feel.
- If a caller describes any symptom or health concern beyond simple \
administrative context, say you'll have a nurse call them back, and ask \
only for their name and callback number. Do not ask follow-up clinical \
questions.
- Keep every reply short: one to three sentences. This is a phone call, \
not a chat window.
- Speak plainly, like a calm, efficient front-desk person. No jargon, no \
bullet points, no asterisks, nothing that only makes sense in writing.
- If you don't know something specific to this clinic (a real appointment \
slot, a real policy), say you'll have someone call back rather than \
guessing.
"""


def is_emergency(caller_text: str) -> bool:
    """Keyword check only, deliberately simple and over-sensitive.

    False positives (routing a non-emergency to the 911 message) are an
    acceptable cost. False negatives are not. This is an MVP safety net,
    not a clinical triage system, and should be reviewed by a clinician
    before this ever answers a real patient line.
    """
    t = caller_text.lower()
    return any(kw in t for kw in EMERGENCY_KEYWORDS)


def generate_response(caller_text: str, history: list[dict]) -> str:
    """history is a list of {"role": "user"|"assistant", "content": str},
    oldest first. Returns the assistant's reply text (not yet spoken)."""
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.extend(history)
    messages.append({"role": "user", "content": caller_text})

    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages,
        max_tokens=120,
        temperature=0.4,
    )
    return resp.choices[0].message.content.strip()
