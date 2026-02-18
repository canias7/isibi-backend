import os
import json
import asyncio
import websockets
import logging
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
from google_calendar import check_availability, create_appointment, list_appointments

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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
    # Twilio sends form data, not JSON
    form_data = await request.form()
    
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
    ws_url = f"wss://{DOMAIN}/media-stream"
    print(f"WebSocket URL: {ws_url}")
    print(f"DOMAIN env var: {DOMAIN}")
    print(f"Agent ID: {agent['id']}")
    
    vr = VoiceResponse()
    connect = Connect()
    stream = connect.stream(url=ws_url)
    # Pass agent_id as a custom parameter (accessible in customParameters)
    stream.parameter(name="agent_id", value=str(agent['id']))
    vr.append(connect)
    
    twiml_response = str(vr)
    print(f"TwiML Response: {twiml_response}")
    
    return HTMLResponse(twiml_response, media_type="application/xml")

@app.on_event("startup")
async def startup_event():
    init_db()
    print("=" * 60)
    print("🚀 APP STARTUP - VERSION: FIRST_MESSAGE_FIX_v2")
    print("=" * 60)

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

print("📋 Registered routes:")
for route in app.routes:
    print(f"  - {route.path} ({route.methods if hasattr(route, 'methods') else 'WebSocket'})")

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
    logger.info("=" * 50)
    logger.info("🔌 WebSocket connection attempt")
    
    try:
        await websocket.accept()
        logger.info("✅ WebSocket accepted")
    except Exception as e:
        logger.error(f"❌ WebSocket accept failed: {e}")
        raise

    # Twilio doesn't pass URL query params to WebSocket
    # We'll get agent_id from the 'start' event's customParameters instead
    agent_id = None
    agent = None
    first_message = None
    
    # Default values (will be updated when we receive the start event)
    instructions = SYSTEM_MESSAGE
    voice = VOICE
    tools = None

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
            nonlocal stream_sid, latest_media_timestamp, response_start_timestamp_twilio, last_assistant_item, first_message_sent, agent_id, agent, first_message

            try:
                async for message in websocket.iter_text():
                    data = json.loads(message)

                    evt = data.get("event")

                    if evt == "start":
                        stream_sid = data["start"]["streamSid"]
                        custom = data["start"].get("customParameters") or {}
                        agent_id = custom.get("agent_id")
                        
                        logger.info(f"▶️ start streamSid={stream_sid}")
                        logger.info(f"📦 customParameters: {custom}")
                        logger.info(f"🆔 agent_id from customParameters: {agent_id}")
                        
                        # Load agent configuration
                        if agent_id:
                            try:
                                agent = get_agent_by_id(int(agent_id))
                                logger.info(f"✅ Agent loaded: {agent.get('name') if agent else None}")
                                
                                if agent:
                                    first_message = agent.get("first_message")
                                    logger.info(f"🎤 first_message loaded: '{first_message}'")
                                    
                                    # Update session with agent's configuration
                                    agent_instructions = agent.get("system_prompt") or SYSTEM_MESSAGE
                                    agent_voice = agent.get("voice") or VOICE
                                    
                                    # Parse tools - must be array for OpenAI, not object
                                    tools_raw = agent.get("tools_json") or "null"
                                    try:
                                        parsed_tools = json.loads(tools_raw)
                                        # If tools is a dict/object, convert to None (OpenAI expects array or null)
                                        if isinstance(parsed_tools, dict):
                                            agent_tools = []
                                        elif isinstance(parsed_tools, list):
                                            agent_tools = parsed_tools
                                        else:
                                            agent_tools = []
                                    except:
                                        agent_tools = []
                                    
                                    # Add Google Calendar tools if connected
                                    calendar_tools = get_calendar_tools(int(agent_id))
                                    if calendar_tools:
                                        agent_tools.extend(calendar_tools)
                                        logger.info(f"📅 Google Calendar tools enabled ({len(calendar_tools)} functions)")
                                    
                                    # Convert to None if still empty
                                    if not agent_tools:
                                        agent_tools = None
                                    
                                    # Validate voice - if it's "string" or invalid, use default
                                    valid_voices = ['alloy', 'ash', 'ballad', 'coral', 'echo', 'sage', 'shimmer', 'verse', 'marin', 'cedar']
                                    if agent_voice not in valid_voices:
                                        logger.warning(f"⚠️ Invalid voice '{agent_voice}', using default 'alloy'")
                                        agent_voice = 'alloy'
                                    
                                    logger.info(f"📝 System prompt loaded (length: {len(agent_instructions)} chars)")
                                    logger.info(f"📝 System prompt preview: {agent_instructions[:200]}...")
                                    logger.info(f"🎙️ Using voice: {agent_voice}")
                                    
                                    # Send session.update to apply agent config
                                    await initialize_session(
                                        openai_ws,
                                        instructions=agent_instructions,
                                        voice=agent_voice,
                                        tools=agent_tools
                                    )
                                    logger.info("🔄 OpenAI session updated with agent config")
                            except Exception as e:
                                logger.error(f"❌ Error loading agent: {e}")

                        # Reset per-call state
                        response_start_timestamp_twilio = None
                        latest_media_timestamp = 0
                        last_assistant_item = None
                        
                        # Send first message if configured
                        if first_message and not first_message_sent:
                            logger.info(f"📢 Sending first message: {first_message}")
                            # Use response.create with input directly to force exact message
                            await openai_ws.send(json.dumps({
                                "type": "response.create",
                                "response": {
                                    "modalities": ["audio", "text"],
                                    "instructions": f"Say exactly this and nothing else: '{first_message}'"
                                }
                            }))
                            first_message_sent = True
                            logger.info("📢 First message sent successfully")

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
                    
                    # Log errors with full details
                    if rtype == "error":
                        error_details = resp.get("error", {})
                        logger.error(f"❌ OpenAI Error: {error_details}")
                        logger.error(f"Full error response: {resp}")

                    # Handle function calls (Google Calendar)
                    if rtype == "response.function_call_arguments.done":
                        call_id = resp.get("call_id")
                        func_name = resp.get("name")
                        arguments = resp.get("arguments")
                        
                        logger.info(f"📞 Function call: {func_name} with args: {arguments}")
                        
                        try:
                            args = json.loads(arguments)
                            result = None
                            
                            # Execute the calendar function
                            if func_name == "check_availability":
                                result = check_availability(
                                    agent_id=int(agent_id),
                                    date=args.get("date"),
                                    time=args.get("time"),
                                    duration_minutes=args.get("duration_minutes", 30)
                                )
                            elif func_name == "create_appointment":
                                result = create_appointment(
                                    agent_id=int(agent_id),
                                    date=args.get("date"),
                                    time=args.get("time"),
                                    duration_minutes=args.get("duration_minutes"),
                                    customer_name=args.get("customer_name"),
                                    customer_phone=args.get("customer_phone"),
                                    notes=args.get("notes", "")
                                )
                            elif func_name == "list_appointments":
                                result = list_appointments(
                                    agent_id=int(agent_id),
                                    date=args.get("date")
                                )
                            
                            if result:
                                # Send function result back to OpenAI
                                await openai_ws.send(json.dumps({
                                    "type": "conversation.item.create",
                                    "item": {
                                        "type": "function_call_output",
                                        "call_id": call_id,
                                        "output": json.dumps(result)
                                    }
                                }))
                                
                                # Request AI response with function result
                                await openai_ws.send(json.dumps({"type": "response.create"}))
                                
                                logger.info(f"✅ Function result sent: {result}")
                                
                        except Exception as e:
                            logger.error(f"❌ Function call error: {e}")

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


def get_calendar_tools(agent_id: int) -> list:
    """
    Return OpenAI function definitions for Google Calendar if connected.
    Returns empty list if calendar not connected.
    """
    # Check if agent has calendar connected
    from db import get_conn
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT google_calendar_credentials FROM agents WHERE id = ?",
        (agent_id,)
    )
    row = cur.fetchone()
    conn.close()
    
    if not row or not row[0]:
        return []
    
    # Calendar is connected - return tool definitions
    return [
        {
            "type": "function",
            "name": "check_availability",
            "description": "Check if a time slot is available in the calendar. Use this before booking appointments.",
            "parameters": {
                "type": "object",
                "properties": {
                    "date": {
                        "type": "string",
                        "description": "Date in YYYY-MM-DD format (e.g., 2024-03-15)"
                    },
                    "time": {
                        "type": "string",
                        "description": "Time in HH:MM 24-hour format (e.g., 14:30 for 2:30 PM)"
                    },
                    "duration_minutes": {
                        "type": "integer",
                        "description": "Duration of appointment in minutes (default 30)"
                    }
                },
                "required": ["date", "time"]
            }
        },
        {
            "type": "function",
            "name": "create_appointment",
            "description": "Create a new appointment in the calendar after confirming availability.",
            "parameters": {
                "type": "object",
                "properties": {
                    "date": {
                        "type": "string",
                        "description": "Date in YYYY-MM-DD format"
                    },
                    "time": {
                        "type": "string",
                        "description": "Time in HH:MM 24-hour format"
                    },
                    "duration_minutes": {
                        "type": "integer",
                        "description": "Duration in minutes"
                    },
                    "customer_name": {
                        "type": "string",
                        "description": "Customer's full name"
                    },
                    "customer_phone": {
                        "type": "string",
                        "description": "Customer's phone number"
                    },
                    "notes": {
                        "type": "string",
                        "description": "Additional notes or reason for appointment"
                    }
                },
                "required": ["date", "time", "duration_minutes", "customer_name", "customer_phone"]
            }
        },
        {
            "type": "function",
            "name": "list_appointments",
            "description": "List all appointments for a specific date.",
            "parameters": {
                "type": "object",
                "properties": {
                    "date": {
                        "type": "string",
                        "description": "Date in YYYY-MM-DD format"
                    }
                },
                "required": ["date"]
            }
        }
    ]


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
            "turn_detection": {
                "type": "server_vad",
                "threshold": 0.5,  # Sensitivity: 0.0-1.0 (higher = less sensitive)
                "prefix_padding_ms": 300,  # Audio to include before speech starts
                "silence_duration_ms": 1000  # Wait 1 second of silence before responding (default is 500ms)
            },
        },
    }

    if tools:
        session_update["session"]["tools"] = tools
        
    await openai_ws.send(json.dumps(session_update))
    
    
