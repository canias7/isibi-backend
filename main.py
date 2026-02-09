import os
import json
import asyncio
import websockets
from db import get_agent_prompt, init_db
from prompt_api import router as prompt_router
from fastapi import FastAPI, WebSocket, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.websockets import WebSocketDisconnect
from twilio.twiml.voice_response import VoiceResponse, Connect
from dotenv import load_dotenv
from admin_ui import router as admin_router
from auth_routes import router as auth_router
from portal import router as portal_router

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
PORT = int(os.getenv("PORT", 5050))
TEMPERATURE = float(os.getenv("TEMPERATURE", 0.8))

init_db()

SYSTEM_MESSAGE = (
    "You are a helpful and bubbly AI assistant who loves to chat about "
    "anything the user is interested in and is prepared to offer them facts. "
    "You have a penchant for dad jokes, owl jokes, and rickrolling – subtly. "
    "Always stay positive, but work in a joke when appropriate."
)

VOICE = "alloy"
SHOW_TIMING_MATH = False

# Some common event types to log (optional)
LOG_EVENT_TYPES = {
    "error",
    "rate_limits.updated",
    "response.done",
    "input_audio_buffer.committed",
    "input_audio_buffer.speech_started",
    "input_audio_buffer.speech_stopped",
    "session.created",
    "session.updated",
}

app = FastAPI()

from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # later restrict to lovable domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(prompt_router)
app.include_router(admin_router)
app.include_router(auth_router)
app.include_router(portal_router)

if not OPENAI_API_KEY:
    raise ValueError("Missing OPENAI_API_KEY in .env")


from fastapi.responses import HTMLResponse

@app.get("/", response_class=HTMLResponse)
async def home():
    return """
    <html>
      <head>
        <title>ISIBI.AI Control Hub</title>
      </head>
      <body style="font-family: Arial; padding: 40px;">
        <h1>ISIBI.AI Control Hub</h1>

        <p>Main system dashboard:</p>

        <ul>
          <li><a href="/admin">Admin Prompt Builder</a></li>
          <li><a href="/docs">API Docs</a></li>
          <li><a href="/portal">Customer Portal (coming)</a></li>
        </ul>

      </body>
    </html>
    """

@app.api_route("/incoming-call", methods=["GET", "POST"])
async def handle_incoming_call(request: Request):
    form = await request.form()
    to_number = form.get("To")
    tenant_phone = to_number
    print("Incoming call TO:", to_number)

    vr = VoiceResponse()

    vr.say(
        "Please wait while we connect your call to the A I voice assistant.",
        voice="Google.en-US-Chirp3-HD-Aoede",
    )

    vr.pause(length=1)

    vr.say(
        "O.K. you can start talking!",
        voice="Google.en-US-Chirp3-HD-Aoede",
    )

    host = request.headers.get("host")

    connect = Connect()
    stream = connect.stream(url=f"wss://{host}/media-stream?tenant={to_number}")

    if tenant_phone:
        stream.parameter(name="tenant_phone", value=tenant_phone)

    vr.append(connect)

    # ✅ keep call alive
    vr.pause(length=600)

    return HTMLResponse(content=str(vr), media_type="application/xml")

    """
    Twilio webhook. Returns TwiML that starts a Media Stream to /media-stream.
    We pass tenant_phone (the called number) via customParameters.
    """
    # Twilio usually POSTs form-encoded
    form = await request.form()
    tenant_phone = form.get("To")  # the Twilio number being called

    vr = VoiceResponse()
    vr.say(
        "Please wait while we connect your call to the A I voice assistant.",
        voice="Google.en-US-Chirp3-HD-Aoede",
    )
    vr.pause(length=1)
    vr.say("O.K. you can start talking!", voice="Google.en-US-Chirp3-HD-Aoede")

    # IMPORTANT: use Host header so we get the real ngrok domain, not localhost
    host = request.headers.get("host")
    connect = Connect()
    stream = connect.stream(url=f"wss://{host}/media-stream?tenant={to_number}")

    # Pass tenant identifier to websocket start event
    if tenant_phone:
        stream.parameter(name="tenant_phone", value=tenant_phone)

    vr.append(connect)
    return HTMLResponse(content=str(vr), media_type="application/xml")


@app.websocket("/media-stream")
async def handle_media_stream(websocket: WebSocket):
    """
    Twilio <-> OpenAI Realtime bridge.
    """
    await websocket.accept()
    tenant = websocket.query_params.get("tenant")
    db_prompt = get_agent_prompt(tenant) if tenant else None
    instructions = db_prompt or SYSTEM_MESSAGE

    print("Tenant:", tenant)
    print("Using DB prompt:", bool(db_prompt))
    print("✅ Twilio WS connected")

    # OpenAI Realtime websocket
    realtime_url = (
        f"wss://api.openai.com/v1/realtime?model=gpt-realtime&temperature={TEMPERATURE}"
    )

    async with websockets.connect(
        realtime_url,
        additional_headers={
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "OpenAI-Beta": "realtime=v1",
        },
    ) as openai_ws:
        await initialize_session(openai_ws, instructions=instructions)

        stream_sid = None
        latest_media_timestamp = 0
        last_assistant_item = None
        mark_queue = []
        response_start_timestamp_twilio = None

        async def send_mark():
            if not stream_sid:
                return
            await websocket.send_text(
                json.dumps(
                    {
                        "event": "mark",
                        "streamSid": stream_sid,
                        "mark": {"name": "responsePart"},
                    }
                )
            )
            mark_queue.append("responsePart")

        async def handle_speech_started_event():
            nonlocal response_start_timestamp_twilio, last_assistant_item, mark_queue

            # Only truncate if we actually have an in-progress assistant audio item
            if not last_assistant_item:
                return

            if response_start_timestamp_twilio is None:
                return

            elapsed_time = latest_media_timestamp - response_start_timestamp_twilio
            if SHOW_TIMING_MATH:
                print(
                    f"Truncate math: {latest_media_timestamp} - {response_start_timestamp_twilio} = {elapsed_time}ms"
                )

            # Ask OpenAI to truncate the last audio item
            truncate_event = {
                "type": "conversation.item.truncate",
                "item_id": last_assistant_item,
                "content_index": 0,
                "audio_end_ms": max(0, elapsed_time),
            }
            await openai_ws.send(json.dumps(truncate_event))

            # Clear Twilio buffer so it stops playing the old audio
            await websocket.send_text(
                json.dumps({"event": "clear", "streamSid": stream_sid})
            )

            mark_queue.clear()
            last_assistant_item = None
            response_start_timestamp_twilio = None

        async def receive_from_twilio():
            nonlocal stream_sid, latest_media_timestamp, response_start_timestamp_twilio, last_assistant_item

            try:
                async for message in websocket.iter_text():
                    data = json.loads(message)

                    evt = data.get("event")

                    if evt == "start":
                        stream_sid = data["start"]["streamSid"]
                        custom = data["start"].get("customParameters") or {}
                        tenant_phone = custom.get("tenant_phone")
                        print(f"▶️ start streamSid={stream_sid} tenant_phone={tenant_phone}")

                        # Reset per-call state
                        response_start_timestamp_twilio = None
                        latest_media_timestamp = 0
                        last_assistant_item = None

                    elif evt == "media":
                        # Track timestamp so truncation math works
                        try:
                            latest_media_timestamp = int(data["media"].get("timestamp", 0))
                        except Exception:
                            latest_media_timestamp = 0

                        # Forward audio to OpenAI (Twilio sends base64 G.711 u-law)
                        await openai_ws.send(
                            json.dumps(
                                {
                                    "type": "input_audio_buffer.append",
                                    "audio": data["media"]["payload"],
                                }
                            )
                        )

                    elif evt == "mark":
                        if mark_queue:
                            mark_queue.pop(0)

                    elif evt == "stop":
                        print("⏹️ stop received")
                        break

            except WebSocketDisconnect:
                print("❌ Twilio WS disconnected")
                try:
                    await openai_ws.close()
                except Exception:
                    pass

        async def send_to_twilio():
            nonlocal response_start_timestamp_twilio, last_assistant_item

            try:
                async for openai_message in openai_ws:
                    resp = json.loads(openai_message)
                    rtype = resp.get("type")

                    if rtype in LOG_EVENT_TYPES:
                        print("OpenAI event:", rtype)

                    # 1) Stream audio back to Twilio
                    if rtype in ("response.output_audio.delta", "response.audio.delta"):
                        audio_b64 = resp.get("delta")
                        if not audio_b64 or not stream_sid:
                            continue

                        # Detect new assistant item to start truncation timer
                        item_id = resp.get("item_id")
                        if item_id and item_id != last_assistant_item:
                            response_start_timestamp_twilio = latest_media_timestamp
                            last_assistant_item = item_id

                        await websocket.send_text(
                            json.dumps(
                                {
                                    "event": "media",
                                    "streamSid": stream_sid,
                                    "media": {"payload": audio_b64},
                                }
                            )
                        )
                        await send_mark()

                    # 2) If caller starts speaking, interrupt assistant
                    if rtype == "input_audio_buffer.speech_started":
                        print("🗣️ speech_started → interrupt")
                        await handle_speech_started_event()

                    # ✅ When caller stops speaking, ask the model to respond
                    if rtype == "input_audio_buffer.speech_stopped":
                        print("🛑 speech_stopped → commit + response.create")
                        await openai_ws.send(json.dumps({"type": "input_audio_buffer.commit"}))
                        await openai_ws.send(json.dumps({"type": "response.create"}))

            except Exception as e:
                print(f"Error in send_to_twilio: {e}")

        await asyncio.gather(receive_from_twilio(), send_to_twilio())


async def initialize_session(openai_ws, instructions: str):
    """
    Configure OpenAI Realtime session for Twilio Media Streams (G.711 u-law).
    """
    session_update = {
        "type": "session.update",
        "session": {
            "modalities": ["audio", "text"],
            "input_audio_format": "g711_ulaw",
            "output_audio_format": "g711_ulaw",
            "voice": VOICE,
            "instructions": instructions,
            "turn_detection": {"type": "server_vad"},
        },
    }
    await openai_ws.send(json.dumps(session_update))


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=PORT)
