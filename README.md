# AI Agents for Healthcare — Course Code

Code companion to the "AI Agents for Healthcare" course: real, working
projects built with AI coding agents, for healthcare professionals with no
prior coding background. Each project here is built and tested first, then
the course is built around it, lesson by lesson, so every step you follow
is code that actually runs.

## Projects

- **[`ai-receptionist/`](ai-receptionist/)** — an AI phone receptionist for
  a clinic front desk, built with Twilio (telephony) and ElevenLabs
  (voice). Handles scheduling, hours, and insurance questions; takes a
  message for anything clinical; always escalates anything that sounds
  like a real emergency straight to 911, never to the AI.
- More projects (an AI fax intake tool, and a shared clinical reasoning
  backend both projects can call into) are planned and will land here as
  they're built and tested.

## How to use this repo

Clone it, open the project folder for the lesson you're on, and follow
that folder's own README. Each project explains its own setup: which
accounts you need, where your API keys go, and how to run it.

```bash
git clone https://github.com/<org-or-user>/ai-agents-for-healthcare-course.git
```

## A note on what this is, and isn't

This code is written for teaching. It demonstrates how the pieces fit
together, not a finished, compliance-reviewed clinical product. Before
anything in this repo touches a real patient, at minimum: get signed
Business Associate Agreements with every third-party service involved,
have a clinician review any safety-relevant logic (such as the emergency
keyword list), and confirm call-recording consent requirements for your
state. Every project's own README repeats the specific version of this
warning that applies to it.

## License

This code is published for people following the course to read, run, and
learn from. All rights reserved: please don't repackage or resell it as
your own course or product. Ask first if you want to use it some other
way.
