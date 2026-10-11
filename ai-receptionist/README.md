# AI Clinic Receptionist

An AI phone receptionist for a clinic front desk. A caller rings a Twilio
number, speaks naturally, and an LLM (currently OpenAI's `gpt-4o-mini`,
swappable for Claude) decides what to say back. ElevenLabs turns that
reply into a real voice.

**What it handles:** appointment scheduling, clinic hours, location,
insurance, and taking a message for a prescription refill or a nurse
callback.

**What it never does:** give medical advice, discuss symptoms, or
diagnose anything. Any question that drifts into clinical territory gets
"I'll have a nurse call you back," not an answer. See the system prompt
in `brain.py` for the exact rules.

**Emergencies never reach the AI.** `brain.is_emergency()` checks the
caller's words against a keyword list (chest pain, suicidal language,
severe bleeding, and so on) *before* anything goes to the LLM. A match
skips straight to a fixed message telling the caller to hang up and call
911. This check is deliberately simple and deliberately over-sensitive: a
false alarm costs nothing, a miss could cost a lot. **Have a clinician
review and extend this keyword list before this ever answers a real
line.**

## Setup

1. **Clone this repo and enter this folder:**
   ```bash
   cd ai-receptionist
   ```
2. **Create a virtual environment and install dependencies:**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate      # Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   ```
3. **Copy the example environment file and fill in your own keys:**
   ```bash
   cp .env.example .env
   ```
   - `OPENAI_API_KEY` — platform.openai.com
   - `ELEVENLABS_API_KEY` — elevenlabs.io (the free tier is enough to test)
   - `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_PHONE_NUMBER` — a
     free Twilio trial account gives you a working number to test with,
     see twilio.com

   **Never commit your real `.env` file.** `.gitignore` already excludes
   it, but double-check before you push anywhere.

## Run it without a phone call

You don't need Twilio to check that the brain and the voice both work:

```bash
python test_local.py
```

This calls the real OpenAI and ElevenLabs APIs, checks the assistant
stays in scope and refuses to give medical advice, generates real audio,
and drives the exact same FastAPI request cycle Twilio would use — all
without placing a call.

## Run it for a real phone call

1. Start the server:
   ```bash
   uvicorn main:app --reload
   ```
2. In another terminal, expose it publicly with a tunnel (ngrok is the
   easiest option):
   ```bash
   ngrok http 8000
   ```
   Copy the `https://...ngrok-free.app` URL it gives you.
3. Set `PUBLIC_BASE_URL` in `.env` to that URL, and restart the server so
   it picks up the change.
4. In the Twilio Console, open your phone number's settings and set "A
   call comes in" to a webhook pointing at `<your ngrok URL>/voice`,
   method POST.
5. Call the number. Twilio handles the actual phone network; this app
   just decides what to say.

## Known limitations (why this isn't production yet)

- Conversation history is kept in memory and is lost on restart, and
  won't work correctly if you ever run more than one server process.
  Production needs Redis or a database instead.
- The emergency keyword list is a safety net, not a clinical triage
  system, and hasn't been reviewed by a clinician.
- No Business Associate Agreement is assumed with any provider here. A
  real deployment touching real patient information needs one with every
  service involved (Twilio, ElevenLabs, OpenAI or Anthropic) before it
  goes live.
- Call recording consent laws vary by state; check yours before using
  this with real callers.
