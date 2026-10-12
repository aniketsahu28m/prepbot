"""Voice version: same agents, but the ones that talk use a Gemini Live model.
In `adk web`, pick this app and press the microphone button."""

import os

from interview_coach.agent import build_root

LIVE_MODEL = os.getenv("LIVE_MODEL", "gemini-3.1-flash-live-preview")

root_agent = build_root(speaking_model=LIVE_MODEL)
