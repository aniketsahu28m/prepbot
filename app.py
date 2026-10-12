"""PrepBot web app. Run `python app.py`, then open http://localhost:8000."""

import asyncio
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).parent
load_dotenv(ROOT / ".env")  # before importing agents: they read model names from env
sys.path.insert(0, str(ROOT / "agents"))

from fastapi import FastAPI, WebSocket, WebSocketDisconnect  # noqa: E402
from fastapi.responses import FileResponse, JSONResponse  # noqa: E402
from google.adk.agents.live_request_queue import LiveRequestQueue  # noqa: E402
from google.adk.agents.run_config import RunConfig  # noqa: E402
from google.adk.runners import Runner  # noqa: E402
from google.adk.sessions import InMemorySessionService  # noqa: E402
from google.genai import types  # noqa: E402
from pydantic import BaseModel  # noqa: E402

from interview_coach.agent import build_interviewer, build_root  # noqa: E402

APP, USER = "prepbot", "local"
LIVE_MODEL = os.getenv("LIVE_MODEL", "gemini-3.1-flash-live-preview")

# ponytail: in-memory sessions, single local user; lost on restart (results are saved to sessions/).
sessions = InMemorySessionService()
text_runner = Runner(app_name=APP, agent=build_root(), session_service=sessions)
voice_runner = Runner(app_name=APP, agent=build_interviewer(LIVE_MODEL, standalone=True),
                      session_service=sessions)
app = FastAPI()


class Msg(BaseModel):
    session_id: str | None = None
    text: str


def friendly_error(e: Exception) -> JSONResponse:
    msg = str(e)
    if "429" in msg or "RESOURCE_EXHAUSTED" in msg:
        text = ("You've hit Gemini's usage limit for your API key (free keys allow about 20 "
                "requests per model per day). Turn on billing in Google AI Studio or try again tomorrow.")
    elif "503" in msg or "UNAVAILABLE" in msg:
        text = "Google's AI servers are busy right now. Wait a minute and try again."
    elif "API key" in msg or "401" in msg or "403" in msg:
        text = "Your API key was rejected. Check GOOGLE_API_KEY in the .env file (see README)."
    else:
        text = f"Something went wrong: {msg[:300]}"
    return JSONResponse({"error": text}, status_code=500)


async def ask(session_id: str, text: str) -> dict:
    """Sends one user message through the agent team and returns what they said."""
    replies = []
    async for e in text_runner.run_async(
        user_id=USER, session_id=session_id,
        new_message=types.Content(role="user", parts=[types.Part(text=text)]),
    ):
        if e.partial or not e.content or e.author == "user":
            continue
        # Only the agents that talk to the candidate; worker output lands in state.
        if e.author in ("interview_coach", "interviewer"):
            replies += [p.text for p in e.content.parts or [] if p.text]
    s = await sessions.get_session(app_name=APP, user_id=USER, session_id=session_id)
    return {"session_id": session_id, "replies": replies,
            **{k: s.state.get(k) for k in ("plan", "scores", "report")}}


@app.get("/")
def index():
    return FileResponse(ROOT / "static" / "index.html")


@app.post("/api/plan")
async def plan(m: Msg):
    s = await sessions.create_session(app_name=APP, user_id=USER)
    try:
        return await ask(s.id, m.text + "\n\nMake the interview plan and summarise it. "
                         "Don't start the interview until I say I'm ready.")
    except Exception as e:
        return friendly_error(e)


@app.post("/api/chat")
async def chat(m: Msg):
    try:
        return await ask(m.session_id, m.text)
    except Exception as e:
        return friendly_error(e)


@app.post("/api/finish")
async def finish(m: Msg):
    try:
        return await ask(m.session_id, "I'd like to end the interview now. "
                         "Please score my answers and write my coaching report.")
    except Exception as e:
        return friendly_error(e)


@app.websocket("/ws/{session_id}")
async def voice(ws: WebSocket, session_id: str):
    """Browser sends 16 kHz PCM mic audio (binary); we send back 24 kHz PCM audio
    (binary) plus JSON transcript lines."""
    await ws.accept()
    queue = LiveRequestQueue()
    config = RunConfig(
        response_modalities=["AUDIO"],
        input_audio_transcription=types.AudioTranscriptionConfig(),
        output_audio_transcription=types.AudioTranscriptionConfig(),
    )
    queue.send_content(types.Content(role="user", parts=[types.Part(
        text="I'm ready. Please start the interview with your first question.")]))

    async def upstream():
        while True:
            msg = await ws.receive()
            if msg["type"] == "websocket.disconnect":
                return
            if msg.get("bytes"):
                queue.send_realtime(types.Blob(data=msg["bytes"], mime_type="audio/pcm;rate=16000"))

    async def downstream():
        async for e in voice_runner.run_live(user_id=USER, session_id=session_id,
                                             live_request_queue=queue, run_config=config):
            for p in (e.content.parts if e.content else None) or []:
                if p.inline_data and p.inline_data.data:
                    await ws.send_bytes(p.inline_data.data)
            for role, t in (("you", e.input_transcription), ("bot", e.output_transcription)):
                if t and t.text and not e.partial:
                    await ws.send_text(json.dumps({"role": role, "text": t.text}))
            if e.interrupted:
                await ws.send_text(json.dumps({"interrupted": True}))

    try:
        done, pending = await asyncio.wait([asyncio.create_task(upstream()),
                                            asyncio.create_task(downstream())],
                                           return_when=asyncio.FIRST_COMPLETED)
        for t in pending:
            t.cancel()
        for t in done:
            if t.exception() and not isinstance(t.exception(), WebSocketDisconnect):
                await ws.send_text(json.dumps({"error": json.loads(
                    friendly_error(t.exception()).body)["error"]}))
    except Exception:
        pass
    finally:
        queue.close()


if __name__ == "__main__":
    import uvicorn
    if not os.getenv("GOOGLE_API_KEY") or "paste-your-key" in os.getenv("GOOGLE_API_KEY", ""):
        sys.exit("No API key found. Follow 'Add your API key' in README.md, then run this again.")
    print("\n  PrepBot is running. Open http://localhost:8000 in Chrome.\n  Press Ctrl+C to stop.\n")
    uvicorn.run(app, host="127.0.0.1", port=int(os.getenv("PORT", 8000)), log_level="warning")
