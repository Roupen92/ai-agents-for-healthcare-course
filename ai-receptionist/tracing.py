"""
Structured tracing: one log line per meaningful step in a call, every
line tagged with the same call_sid, so a log file can be filtered down
to the complete, in-order story of one specific call. This is what
"observability" means in practice: being able to answer "what actually
happened on this call" after the fact, without having watched it live.

Deliberately never logs the caller's actual words or the assistant's
actual reply, only metadata: which step ran, how long it took, whether
it succeeded. A log is still a record that could leak PHI if you're not
careful what goes into it. See the HIPAA section of the course.
"""

import json
import logging
import time
from contextlib import contextmanager

logger = logging.getLogger("receptionist.trace")
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False


def trace(call_sid: str, step: str, **fields) -> None:
    """One trace line. `fields` is metadata only, never caller text or
    an assistant reply — durations, booleans, counts, error types."""
    logger.info(json.dumps({"call_sid": call_sid, "step": step, **fields}))


@contextmanager
def traced_step(call_sid: str, step: str):
    """Wraps a block of code that calls out to something slow (OpenAI,
    ElevenLabs). Logs how long it took and whether it raised, without
    ever touching what was actually said. Use as:

        with traced_step(call_sid, "llm_response"):
            reply = generate_response(...)
    """
    start = time.monotonic()
    try:
        yield
    except Exception as e:
        trace(call_sid, step, ok=False,
              duration_ms=round((time.monotonic() - start) * 1000),
              error=type(e).__name__)
        raise
    else:
        trace(call_sid, step, ok=True,
              duration_ms=round((time.monotonic() - start) * 1000))
