import os
import json
import asyncio
import websockets
from db import get_agent_prompt, init_db, get_agent_by_id
from prompt_api import router as prompt_router
from fastapi import FastAPI, WebSocket, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.websockets import WebSocketDisconnect
from twilio.twiml.voice_response import VoiceResponse, Connect
from dotenv import load_dotenv
from auth_routes import router as auth_router
from portal import router as portal_router
from db import create_agent, list_agents, get_agent_by_phone
from pydantic import BaseModel
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from auth import verify_token
from twilio.twiml.voice_response import VoiceResponse, Connect, Stream

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
PORT = int(os.getenv("PORT", 5050))
TEMPERATURE = float(os.getenv("TEMPERATURE", 0.8))
DOMAIN = os.getenv("DOMAIN", "isibi-backend.onrender.com")  # Your public domain or ngrok URL

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

@app.post("/incoming-call")
async def incoming_call(request: Request):
    # Debug: Check content type and body
    print("Content-Type:", request.headers.get("content-type"))
    
    # Try to get the raw body
    try:
        body = await request.body()
        print("Raw body:", body.decode())
    except Exception as e:
        print("Error reading body:", e)
    
    # Twilio sends form data, not JSON
    form_data = await request.form()
    print("Form data keys:", list(form_data.keys()))
    print("Raw form data:", dict(form_data))
    
    called_number = form_data.get("To")
    from_number = form_data.get("From")

    print("=" * 50)
    print("INCOMING CALL")
    print("TWILIO To (raw):", called_number)
    print("TWILIO From:", from_number)

    # Try multiple phone number formats to match database
    agent = None
    if called_number:
        # Try original format first
        agent = get_agent_by_phone(called_number)
        print(f"Lookup with '{called_number}':", bool(agent))
        
        # If not found, try without the + prefix
        if not agent and called_number.startswith("+"):
            no_plus = called_number[1:]
            agent = get_agent_by_phone(no_plus)
            print(f"Lookup with '{no_plus}':", bool(agent))
        
        # If not found, try with + prefix added
        if not agent and not called_number.startswith("+"):
            with_plus = f"+{called_number}"
            agent = get_agent_by_phone(with_plus)
            print(f"Lookup with '{with_plus}':", bool(agent))
    
    print("Agent found:", bool(agent))
    if agent:
        print("Agent ID:", agent.get('id'))
    print("=" * 50)
    
    if not agent:
        vr = VoiceResponse()
        vr.say("No agent is configured on this number.")
        return HTMLResponse(str(vr), media_type="application/xml")

    # Use DOMAIN environment variable for WebSocket URL
    ws_url = f"wss://{DOMAIN}/media-stream?agent_id={agent['id']}"
    print(f"WebSocket URL: {ws_url}")
    print(f"DOMAIN env var: {DOMAIN}")
    
    vr = VoiceResponse()
    connect = Connect()
    connect.stream(url=ws_url)
    vr.append(connect)
    
    twiml_response = str(vr)
    print(f"TwiML Response: {twiml_response}")
    
    return HTMLResponse(twiml_response, media_type="application/xml")

@app.on_event("startup")
async def startup_event():
    init_db()

from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # later restrict to lovable domain
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(prompt_router)
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

@app.websocket("/media-stream")
async def handle_media_stream(websocket: WebSocket):
    """
    Twilio <-> OpenAI Realtime bridge.
    """
    print("=" * 50)
    print("🔌 WebSocket connection attempt")
    print("Query params:", dict(websocket.query_params))
    
    try:
        await websocket.accept()
        print("✅ WebSocket accepted")
    except Exception as e:
        print(f"❌ WebSocket accept failed: {e}")
        raise

    agent_id = websocket.query_params.get("agent_id")

    agent = None
    if agent_id:
        try:
            agent = get_agent_by_id(int(agent_id))
        except Exception as e:
            print("ERROR loading agent:", e)
            agent = None 

    print("WS agent_id:", agent_id)
    print("WS agent found:", bool(agent))
    if agent:
        print("WS system_prompt len:", len(agent.get("system_prompt") or ""))
        print("WS first_message:", agent.get("first_message"))
        print("WS voice:", agent.get("voice"))
        print("WS provider:", agent.get("provider"))
        print("WS tools_json present:", bool(agent.get("tools_json")))

    instructions = (
        agent["system_prompt"]
        if agent and agent.get("system_prompt")
        else SYSTEM_MESSAGE
    )

    voice = agent.get("voice") if agent else None
    tools = json.loads(agent["tools_json"]) if agent and agent.get("tools_json") else None
    provider = agent.get("provider") if agent else None
    first_message = agent.get("first_message") if agent else None
    # settings_json removed - column doesn't exist yet
    db_prompt = get_agent_prompt(agent_id) if agent_id else None

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
        await initialize_session(
            openai_ws,
            instructions=instructions,
            voice=voice,
            tools=tools
        )

        stream_sid = None
        latest_media_timestamp = 0
        last_assistant_item = None
        mark_queue = []
        response_start_timestamp_twilio = None
        first_message_sent = False  # Track if we've sent the greeting

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
            nonlocal stream_sid, latest_media_timestamp, response_start_timestamp_twilio, last_assistant_item, first_message_sent

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
                        
                        # Send first message if configured
                        if first_message and not first_message_sent:
                            print(f"📢 Sending first message: {first_message}")
                            await openai_ws.send(json.dumps({
                                "type": "conversation.item.create",
                                "item": {
                                    "type": "message",
                                    "role": "assistant",
                                    "content": [
                                        {"type": "input_text", "text": first_message}
                                    ]
                                }
                            }))
                            await openai_ws.send(json.dumps({
                                "type": "response.create"
                            }))
                            first_message_sent = True

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

                    # ✅ When caller stops speaking wait one second, ask the model to respond
                    if rtype == "input_audio_buffer.speech_stopped":
                        print("🛑 speech_stopped → commit + response.create")
                        await openai_ws.send(json.dumps({"type": "input_audio_buffer.commit"}))
                        await openai_ws.send(json.dumps({"type": "response.create"}))

            except Exception as e:
                print(f"Error in send_to_twilio: {e}")

        await asyncio.gather(receive_from_twilio(), send_to_twilio())


async def initialize_session(openai_ws, instructions: str, voice: str | None = None, tools: dict | None = None, first_message: str | None = None):
    """
    Configure OpenAI Realtime session for Twilio Media Streams (G.711 u-law).
    """
    session_update = {
        "type": "session.update",
        "session": {
            "modalities": ["audio", "text"],
            "input_audio_format": "g711_ulaw",
            "output_audio_format": "g711_ulaw",
            "voice": voice or VOICE,
            "instructions": instructions,
            "turn_detection": {"type": "server_vad"},
        },
    }

    if tools:
        session_update["session"]["tools"] = tools
        
    await openai_ws.send(json.dumps(session_update))
    
    
