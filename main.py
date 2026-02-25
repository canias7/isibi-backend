import os
import json
import asyncio
import websockets
import logging
from db import get_agent_prompt, init_db, get_agent_by_id, start_call_tracking, end_call_tracking, calculate_call_cost, calculate_call_revenue, get_user_credits, deduct_credits
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
from datetime import datetime
from slack_integration import notify_new_call, notify_call_ended
from teams_integration import notify_new_call_teams, notify_call_ended_teams

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
        call_summary = None  # Store what happened during the call

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
                        
                        # Start tracking this call
                        call_start_time = datetime.now()
                        
                        # Load agent configuration
                        if agent_id:
                            try:
                                agent = get_agent_by_id(int(agent_id))
                                logger.info(f"✅ Agent loaded: {agent.get('name') if agent else None}")
                                
                                # Track call usage
                                if agent:
                                    owner_user_id = agent.get('owner_user_id')
                                    
                                    # Check if user has credits
                                    credits = get_user_credits(owner_user_id)
                                    
                                    if credits["balance"] <= 0:
                                        logger.warning(f"❌ User {owner_user_id} has no credits! Balance: ${credits['balance']} - BLOCKING CALL")
                                        
                                        # Send low balance message
                                        await openai_ws.send(json.dumps({
                                            "type": "response.create",
                                            "response": {
                                                "modalities": ["audio", "text"],
                                                "instructions": "Say exactly: 'I'm sorry, but your account has insufficient credits. Please add credits at your dashboard to continue using this service. Thank you, goodbye.'"
                                            }
                                        }))
                                        
                                        # Wait for message to finish playing (about 8 seconds)
                                        await asyncio.sleep(8)
                                        
                                        logger.info("🚫 Call blocked due to insufficient credits - hanging up")
                                        
                                        # Close OpenAI connection
                                        await openai_ws.close()
                                        
                                        # Close Twilio connection to end call
                                        await twilio_ws.close()
                                        
                                        # Exit the handler
                                        return
                                    else:
                                        logger.info(f"💳 User has ${credits['balance']:.2f} in credits - call proceeding")
                                    
                                    # Get call info from Twilio data
                                    call_from = data["start"].get("callSid", "unknown")
                                    call_to = agent.get("phone_number", "unknown")
                                    
                                    try:
                                        start_call_tracking(
                                            user_id=owner_user_id,
                                            agent_id=int(agent_id),
                                            call_sid=stream_sid,
                                            call_from=call_from,
                                            call_to=call_to
                                        )
                                        logger.info(f"📊 Call tracking started for user {owner_user_id}")
                                        
                                        # Send Slack notification for new call
                                        try:
                                            from db import get_conn, sql
                                            conn = get_conn()
                                            cur = conn.cursor()
                                            cur.execute(sql("""
                                                SELECT slack_bot_token, slack_default_channel, slack_enabled
                                                FROM users WHERE id = {PH}
                                            """), (owner_user_id,))
                                            slack_row = cur.fetchone()
                                            conn.close()
                                            
                                            if slack_row:
                                                if isinstance(slack_row, dict):
                                                    slack_token = slack_row.get('slack_bot_token')
                                                    slack_channel = slack_row.get('slack_default_channel') or '#calls'
                                                    slack_enabled = slack_row.get('slack_enabled')
                                                else:
                                                    slack_token = slack_row[0] if len(slack_row) > 0 else None
                                                    slack_channel = slack_row[1] if len(slack_row) > 1 else '#calls'
                                                    slack_enabled = slack_row[2] if len(slack_row) > 2 else False
                                                
                                                if slack_enabled and slack_token:
                                                    notify_new_call(
                                                        agent_name=agent.get('name', 'Unknown Agent'),
                                                        caller_number=call_from,
                                                        channel=slack_channel,
                                                        token=slack_token
                                                    )
                                                    logger.info("📢 Slack notification sent: New call")
                                        except Exception as e:
                                            logger.warning(f"⚠️ Failed to send Slack notification: {e}")
                                        
                                        # Send Teams notification for new call
                                        try:
                                            conn = get_conn()
                                            cur = conn.cursor()
                                            cur.execute(sql("""
                                                SELECT teams_webhook_url, teams_enabled
                                                FROM users WHERE id = {PH}
                                            """), (owner_user_id,))
                                            teams_row = cur.fetchone()
                                            conn.close()
                                            
                                            if teams_row:
                                                if isinstance(teams_row, dict):
                                                    teams_webhook = teams_row.get('teams_webhook_url')
                                                    teams_enabled = teams_row.get('teams_enabled')
                                                else:
                                                    teams_webhook = teams_row[0] if len(teams_row) > 0 else None
                                                    teams_enabled = teams_row[1] if len(teams_row) > 1 else False
                                                
                                                if teams_enabled and teams_webhook:
                                                    notify_new_call_teams(
                                                        webhook_url=teams_webhook,
                                                        agent_name=agent.get('name', 'Unknown Agent'),
                                                        caller_number=call_from
                                                    )
                                                    logger.info("📢 Teams notification sent: New call")
                                        except Exception as e:
                                            logger.warning(f"⚠️ Failed to send Teams notification: {e}")
                                        
                                    except Exception as e:
                                        logger.error(f"❌ Failed to start call tracking: {e}")
                                
                                if agent:
                                    first_message = agent.get("first_message")
                                    logger.info(f"🎤 first_message loaded: '{first_message}'")
                                    
                                    # Update session with agent's configuration
                                    agent_instructions = agent.get("system_prompt") or SYSTEM_MESSAGE
                                    agent_voice = agent.get("voice") or VOICE
                                    
                                    # Enforce English language unless specified otherwise in system prompt
                                    # Check if language is explicitly mentioned in the system prompt
                                    language_keywords = ['spanish', 'french', 'german', 'italian', 'portuguese', 'chinese', 'japanese', 'korean', 'arabic', 'hindi', 'language:', 'speak in', 'respond in']
                                    has_language_instruction = any(keyword in agent_instructions.lower() for keyword in language_keywords)
                                    
                                    if not has_language_instruction:
                                        # Add English enforcement to the beginning of instructions
                                        english_enforcement = """CRITICAL LANGUAGE REQUIREMENT: You MUST respond ONLY in English to all customers, regardless of what language they speak to you in. If a customer speaks to you in Spanish, Chinese, or any other language, you must respond in English. Do not switch languages. Always use English.

"""
                                        agent_instructions = english_enforcement + agent_instructions
                                        logger.info("🌍 Language enforcement: English-only mode enabled")
                                    else:
                                        logger.info("🌍 Custom language instruction detected in system prompt")
                                    
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
                                    
                                    # Add SMS confirmation tools (always available)
                                    sms_tools = get_sms_tools()
                                    if sms_tools:
                                        agent_tools.extend(sms_tools)
                                        logger.info(f"📱 SMS confirmation tools enabled ({len(sms_tools)} functions)")
                                    
                                    # Add call summary tool (always available)
                                    summary_tools = get_call_summary_tool()
                                    if summary_tools:
                                        agent_tools.extend(summary_tools)
                                        logger.info(f"📋 Call summary tool enabled")
                                    
                                    # Add Square payment tool (always available)
                                    square_tools = get_square_payment_tool()
                                    if square_tools:
                                        agent_tools.extend(square_tools)
                                        logger.info(f"💳 Square payment tool enabled")
                                    
                                    # Add Shopify tools (if user has Shopify configured)
                                    shopify_tools = get_shopify_tools()
                                    if shopify_tools:
                                        agent_tools.extend(shopify_tools)
                                        logger.info(f"🛍️ Shopify tools enabled ({len(shopify_tools)} functions)")
                                    
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
                                    
                                    # Wait a bit for session to be fully configured
                                    await asyncio.sleep(0.5)
                                    
                            except Exception as e:
                                logger.error(f"❌ Error loading agent: {e}")

                        # Reset per-call state
                        response_start_timestamp_twilio = None
                        latest_media_timestamp = 0
                        last_assistant_item = None
                        
                        # Send first message if configured
                        if not first_message_sent:
                            logger.info(f"📢 Triggering automatic greeting from system prompt")
                            
                            # Trigger the AI to start speaking immediately using the greeting from its system prompt
                            await openai_ws.send(json.dumps({
                                "type": "response.create",
                                "response": {
                                    "modalities": ["text", "audio"],
                                    "instructions": "Greet the caller now using the greeting from Section 2 of your system prompt."
                                }
                            }))
                            
                            first_message_sent = True
                            logger.info("📢 Automatic greeting triggered from system prompt")

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
                        
                        # End call tracking
                        if stream_sid and agent:
                            try:
                                call_end_time = datetime.now()
                                duration_seconds = int((call_end_time - call_start_time).total_seconds())
                                
                                # Skip tracking if call was too short (< 1 second)
                                if duration_seconds < 1:
                                    logger.warning(f"⚠️ Call too short to track: {duration_seconds}s")
                                    break
                                
                                # YOUR COST: What you pay (e.g., $0.05/min)
                                cost = calculate_call_cost(duration_seconds, cost_per_minute=0.05)
                                
                                # CUSTOMER CHARGE: 2x your cost = $0.10/min (THIS IS IN CREDITS)
                                credits_to_deduct = calculate_call_revenue(duration_seconds, revenue_per_minute=0.10)
                                
                                # PROFIT: What you make
                                profit = credits_to_deduct - cost
                                
                                logger.info(f"📊 Call ended: {duration_seconds}s")
                                logger.info(f"💰 Cost: ${cost:.4f} | Credits to deduct: ${credits_to_deduct:.4f}")
                                
                                # Save call record
                                end_call_tracking(stream_sid, duration_seconds, cost, credits_to_deduct)
                                logger.info(f"✅ Call tracking saved")
                                
                                # Deduct credits from user's balance
                                owner_user_id = agent.get('owner_user_id')
                                result = deduct_credits(
                                    user_id=owner_user_id,
                                    amount=credits_to_deduct,
                                    description=f"Call to {agent.get('name')} ({duration_seconds}s)"
                                )
                                
                                if result["success"]:
                                    logger.info(f"💳 Remaining balance: ${result['balance']:.2f}")
                                else:
                                    logger.warning(f"⚠️ Credit deduction failed: {result.get('error')}")
                                
                                # Send Slack notification for call ended
                                try:
                                    from db import get_conn, sql
                                    conn = get_conn()
                                    cur = conn.cursor()
                                    cur.execute(sql("""
                                        SELECT slack_bot_token, slack_default_channel, slack_enabled
                                        FROM users WHERE id = {PH}
                                    """), (owner_user_id,))
                                    slack_row = cur.fetchone()
                                    conn.close()
                                    
                                    if slack_row:
                                        if isinstance(slack_row, dict):
                                            slack_token = slack_row.get('slack_bot_token')
                                            slack_channel = slack_row.get('slack_default_channel') or '#calls'
                                            slack_enabled = slack_row.get('slack_enabled')
                                        else:
                                            slack_token = slack_row[0] if len(slack_row) > 0 else None
                                            slack_channel = slack_row[1] if len(slack_row) > 1 else '#calls'
                                            slack_enabled = slack_row[2] if len(slack_row) > 2 else False
                                        
                                        if slack_enabled and slack_token:
                                            # Get call_from from the call tracking
                                            call_from_number = "Unknown"  # Default
                                            try:
                                                conn2 = get_conn()
                                                cur2 = conn2.cursor()
                                                cur2.execute(sql("""
                                                    SELECT call_from FROM call_usage 
                                                    WHERE call_sid = {PH}
                                                """), (stream_sid,))
                                                call_row = cur2.fetchone()
                                                if call_row:
                                                    call_from_number = call_row[0] if isinstance(call_row, tuple) else call_row.get('call_from')
                                                conn2.close()
                                            except:
                                                pass
                                            
                                            notify_call_ended(
                                                agent_name=agent.get('name', 'Unknown Agent'),
                                                caller_number=call_from_number,
                                                duration=duration_seconds,
                                                cost=credits_to_deduct,
                                                channel=slack_channel,
                                                token=slack_token,
                                                summary=call_summary
                                            )
                                            logger.info("📢 Slack notification sent: Call completed")
                                except Exception as e:
                                    logger.warning(f"⚠️ Failed to send Slack notification: {e}")
                                
                                # Send Teams notification for call end
                                try:
                                    from db import get_conn, sql
                                    conn = get_conn()
                                    cur = conn.cursor()
                                    cur.execute(sql("""
                                        SELECT teams_webhook_url, teams_enabled
                                        FROM users WHERE id = {PH}
                                    """), (owner_user_id,))
                                    teams_row = cur.fetchone()
                                    conn.close()
                                    
                                    if teams_row:
                                        if isinstance(teams_row, dict):
                                            teams_webhook = teams_row.get('teams_webhook_url')
                                            teams_enabled = teams_row.get('teams_enabled')
                                        else:
                                            teams_webhook = teams_row[0] if len(teams_row) > 0 else None
                                            teams_enabled = teams_row[1] if len(teams_row) > 1 else False
                                        
                                        if teams_enabled and teams_webhook:
                                            # Get call_from number
                                            call_from_number = "Unknown"
                                            try:
                                                conn2 = get_conn()
                                                cur2 = conn2.cursor()
                                                cur2.execute(sql("""
                                                    SELECT call_from FROM call_usage 
                                                    WHERE call_sid = {PH}
                                                """), (stream_sid,))
                                                call_row = cur2.fetchone()
                                                if call_row:
                                                    call_from_number = call_row[0] if isinstance(call_row, tuple) else call_row.get('call_from')
                                                conn2.close()
                                            except:
                                                pass
                                            
                                            notify_call_ended_teams(
                                                webhook_url=teams_webhook,
                                                agent_name=agent.get('name', 'Unknown Agent'),
                                                caller_number=call_from_number,
                                                duration=duration_seconds,
                                                cost=credits_to_deduct,
                                                summary=call_summary
                                            )
                                            logger.info("📢 Teams notification sent: Call completed")
                                except Exception as e:
                                    logger.warning(f"⚠️ Failed to send Teams notification: {e}")
                                    
                            except Exception as e:
                                logger.error(f"❌ Failed to end call tracking: {e}")
                                import traceback
                                logger.error(traceback.format_exc())
                        
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
                            
                            # Execute SMS functions
                            elif func_name == "send_order_confirmation":
                                logger.info(f"🔔 AI is calling send_order_confirmation tool!")
                                logger.info(f"📋 Args: {args}")
                                
                                from customer_notifications import send_order_confirmation_sms
                                
                                # Get business name and phone number
                                business_name = agent.get('business_name') or agent.get('name', 'Our Business')
                                agent_phone = agent.get('phone_number')
                                
                                logger.info(f"📞 Agent phone: {agent_phone}")
                                logger.info(f"🏢 Business name: {business_name}")
                                
                                result = send_order_confirmation_sms(
                                    customer_phone=args.get("customer_phone"),
                                    business_name=business_name,
                                    order_items=args.get("order_items"),
                                    total=args.get("total"),
                                    pickup_time=args.get("pickup_time"),
                                    delivery_address=args.get("delivery_address"),
                                    order_number=args.get("order_number"),
                                    from_number=agent_phone
                                )
                                logger.info(f"📱 Order confirmation SMS result: {result}")
                            
                            elif func_name == "send_appointment_confirmation":
                                logger.info(f"🔔 AI is calling send_appointment_confirmation tool!")
                                logger.info(f"📋 Args: {args}")
                                
                                from customer_notifications import send_appointment_confirmation_sms
                                
                                business_name = agent.get('business_name') or agent.get('name', 'Our Business')
                                agent_phone = agent.get('phone_number')
                                
                                logger.info(f"📞 Agent phone: {agent_phone}")
                                logger.info(f"🏢 Business name: {business_name}")
                                
                                result = send_appointment_confirmation_sms(
                                    customer_phone=args.get("customer_phone"),
                                    business_name=business_name,
                                    customer_name=args.get("customer_name"),
                                    service=args.get("service"),
                                    date=args.get("date"),
                                    time=args.get("time"),
                                    confirmation_number=args.get("confirmation_number"),
                                    from_number=agent_phone
                                )
                                logger.info(f"📱 Appointment confirmation SMS: {result}")
                            
                            # Log call summary
                            elif func_name == "log_call_summary":
                                nonlocal call_summary
                                call_summary = args.get("summary")
                                outcome = args.get("outcome")
                                
                                logger.info(f"📋 Call summary logged: {call_summary}")
                                logger.info(f"🎯 Outcome: {outcome}")
                                
                                result = {
                                    "success": True,
                                    "message": "Call summary recorded"
                                }
                            
                            # Process Square payment
                            elif func_name == "process_payment":
                                logger.info(f"💳 AI is processing payment via Square!")
                                logger.info(f"💰 Amount: ${args.get('amount')}")
                                
                                from square_integration import create_payment
                                
                                # Convert amount to cents
                                amount_dollars = args.get("amount")
                                amount_cents = int(amount_dollars * 100)
                                
                                result = create_payment(
                                    amount_cents=amount_cents,
                                    card_number=args.get("card_number"),
                                    exp_month=args.get("exp_month"),
                                    exp_year=args.get("exp_year"),
                                    cvv=args.get("cvv"),
                                    postal_code=args.get("postal_code"),
                                    customer_name=args.get("customer_name"),
                                    description=args.get("description"),
                                    reference_id=stream_sid  # Use call SID as reference
                                )
                                
                                if result.get("success"):
                                    logger.info(f"✅ Payment successful! ID: {result.get('payment_id')}")
                                    logger.info(f"💳 Card: ****{result.get('card_last_4')}")
                                else:
                                    logger.error(f"❌ Payment failed: {result.get('error')}")
                            
                            # Shopify product search
                            elif func_name == "search_shopify_products":
                                logger.info(f"🛍️ Searching Shopify products: {args.get('query')}")
                                
                                from shopify_integration import search_products
                                
                                # Get user's Shopify credentials
                                owner_user_id = agent.get('owner_user_id')
                                conn_temp = get_conn()
                                cur_temp = conn_temp.cursor()
                                cur_temp.execute(sql("""
                                    SELECT shopify_shop_name, shopify_access_token
                                    FROM users WHERE id = {PH}
                                """), (owner_user_id,))
                                shop_row = cur_temp.fetchone()
                                conn_temp.close()
                                
                                if shop_row:
                                    if isinstance(shop_row, dict):
                                        shop_name = shop_row.get('shopify_shop_name')
                                        access_token = shop_row.get('shopify_access_token')
                                    else:
                                        shop_name = shop_row[0]
                                        access_token = shop_row[1]
                                    
                                    result = search_products(shop_name, access_token, args.get('query'))
                                    logger.info(f"📦 Found {len(result.get('products', []))} products")
                                else:
                                    result = {"success": False, "error": "Shopify not configured"}
                            
                            # Shopify inventory check
                            elif func_name == "check_shopify_inventory":
                                logger.info(f"📊 Checking inventory for variant {args.get('variant_id')}")
                                
                                from shopify_integration import check_inventory
                                
                                owner_user_id = agent.get('owner_user_id')
                                conn_temp = get_conn()
                                cur_temp = conn_temp.cursor()
                                cur_temp.execute(sql("""
                                    SELECT shopify_shop_name, shopify_access_token
                                    FROM users WHERE id = {PH}
                                """), (owner_user_id,))
                                shop_row = cur_temp.fetchone()
                                conn_temp.close()
                                
                                if shop_row:
                                    if isinstance(shop_row, dict):
                                        shop_name = shop_row.get('shopify_shop_name')
                                        access_token = shop_row.get('shopify_access_token')
                                    else:
                                        shop_name = shop_row[0]
                                        access_token = shop_row[1]
                                    
                                    result = check_inventory(shop_name, access_token, args.get('variant_id'))
                                else:
                                    result = {"success": False, "error": "Shopify not configured"}
                            
                            # Shopify order creation
                            elif func_name == "create_shopify_order":
                                logger.info(f"🛒 Creating Shopify order for {args.get('customer_name')}")
                                
                                from shopify_integration import create_order
                                
                                owner_user_id = agent.get('owner_user_id')
                                conn_temp = get_conn()
                                cur_temp = conn_temp.cursor()
                                cur_temp.execute(sql("""
                                    SELECT shopify_shop_name, shopify_access_token
                                    FROM users WHERE id = {PH}
                                """), (owner_user_id,))
                                shop_row = cur_temp.fetchone()
                                conn_temp.close()
                                
                                if shop_row:
                                    if isinstance(shop_row, dict):
                                        shop_name = shop_row.get('shopify_shop_name')
                                        access_token = shop_row.get('shopify_access_token')
                                    else:
                                        shop_name = shop_row[0]
                                        access_token = shop_row[1]
                                    
                                    result = create_order(
                                        shop_name=shop_name,
                                        access_token=access_token,
                                        customer_email=args.get('customer_email'),
                                        customer_name=args.get('customer_name'),
                                        customer_phone=args.get('customer_phone'),
                                        line_items=args.get('line_items'),
                                        shipping_address=args.get('shipping_address'),
                                        financial_status="paid"  # Assuming payment already processed
                                    )
                                    
                                    if result.get("success"):
                                        logger.info(f"✅ Order created! Order #{result.get('order_number')}")
                                    else:
                                        logger.error(f"❌ Order creation failed: {result.get('error')}")
                                else:
                                    result = {"success": False, "error": "Shopify not configured"}
                            
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
    from db import get_conn, sql
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        sql("SELECT google_calendar_credentials FROM agents WHERE id = {PH}"),
        (agent_id,)
    )
    row = cur.fetchone()
    conn.close()
    
    if not row:
        return []
    
    # Handle both dict (PostgreSQL) and tuple (SQLite)
    creds = row.get('google_calendar_credentials') if isinstance(row, dict) else row[0]
    
    if not creds:
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
                "threshold": 0.7,  # Higher = less sensitive to background noise (0.5 default, 0.7-0.8 for noisy environments)
                "prefix_padding_ms": 300,  # Audio to include before speech starts
                "silence_duration_ms": 800  # Wait longer before considering speech finished (reduces false interruptions)
            },
        },
    }

    if tools:
        session_update["session"]["tools"] = tools
        
    await openai_ws.send(json.dumps(session_update))
    
    


def get_sms_tools() -> list:
    """
    Return OpenAI function definitions for sending customer SMS confirmations.
    Always available (uses Twilio).
    """
    return [
        {
            "type": "function",
            "name": "send_order_confirmation",
            "description": "Send SMS order confirmation to customer after they place an order and provide payment. ALWAYS use this after successfully taking an order.",
            "parameters": {
                "type": "object",
                "properties": {
                    "customer_phone": {
                        "type": "string",
                        "description": "Customer's phone number in E.164 format (e.g., +17045551234)"
                    },
                    "order_items": {
                        "type": "string",
                        "description": "Description of items ordered (e.g., '2 Large Pepperoni Pizzas, Garlic Bread')"
                    },
                    "total": {
                        "type": "number",
                        "description": "Total amount charged including tax and fees"
                    },
                    "pickup_time": {
                        "type": "string",
                        "description": "When order will be ready for pickup (e.g., '6:30 PM')"
                    },
                    "delivery_address": {
                        "type": "string",
                        "description": "Delivery address if applicable"
                    },
                    "order_number": {
                        "type": "string",
                        "description": "Order confirmation number if available"
                    }
                },
                "required": ["customer_phone", "order_items", "total"]
            }
        },
        {
            "type": "function",
            "name": "send_appointment_confirmation",
            "description": "Send SMS appointment confirmation to customer after successfully booking an appointment. ALWAYS use this after booking an appointment.",
            "parameters": {
                "type": "object",
                "properties": {
                    "customer_phone": {
                        "type": "string",
                        "description": "Customer's phone number in E.164 format"
                    },
                    "customer_name": {
                        "type": "string",
                        "description": "Customer's full name"
                    },
                    "service": {
                        "type": "string",
                        "description": "Type of service/appointment (e.g., 'Haircut', 'Dental Cleaning')"
                    },
                    "date": {
                        "type": "string",
                        "description": "Appointment date (e.g., 'February 25, 2026')"
                    },
                    "time": {
                        "type": "string",
                        "description": "Appointment time (e.g., '2:00 PM')"
                    },
                    "confirmation_number": {
                        "type": "string",
                        "description": "Confirmation number if available"
                    }
                },
                "required": ["customer_phone", "customer_name", "service", "date", "time"]
            }
        }
    ]


def get_call_summary_tool() -> list:
    """
    Return OpenAI function definition for logging call summary.
    AI calls this to record what was accomplished during the call.
    """
    return [
        {
            "type": "function",
            "name": "log_call_summary",
            "description": "Log what was accomplished during this call. Call this near the end of the conversation to record the outcome.",
            "parameters": {
                "type": "object",
                "properties": {
                    "summary": {
                        "type": "string",
                        "description": "Brief summary of what was accomplished (e.g., 'Scheduled haircut appointment for Feb 25 at 2pm' or 'Took order for 2 large pizzas, total $28.99, pickup at 6:30pm')"
                    },
                    "outcome": {
                        "type": "string",
                        "enum": ["appointment_scheduled", "order_placed", "question_answered", "escalated", "no_action"],
                        "description": "Primary outcome of the call"
                    }
                },
                "required": ["summary", "outcome"]
            }
        }
    ]


def get_square_payment_tool() -> list:
    """
    Return OpenAI function definition for processing Square payments.
    AI calls this to charge customer's credit card during call.
    """
    return [
        {
            "type": "function",
            "name": "process_payment",
            "description": "Process a credit card payment through Square. Use this after customer provides card details.",
            "parameters": {
                "type": "object",
                "properties": {
                    "amount": {
                        "type": "number",
                        "description": "Total amount to charge in dollars (e.g., 29.99)"
                    },
                    "card_number": {
                        "type": "string",
                        "description": "16-digit credit card number"
                    },
                    "exp_month": {
                        "type": "string",
                        "description": "Expiration month (2 digits, e.g., '12')"
                    },
                    "exp_year": {
                        "type": "string",
                        "description": "Expiration year (4 digits, e.g., '2025')"
                    },
                    "cvv": {
                        "type": "string",
                        "description": "3-digit CVV security code"
                    },
                    "postal_code": {
                        "type": "string",
                        "description": "Billing ZIP code"
                    },
                    "customer_name": {
                        "type": "string",
                        "description": "Cardholder name"
                    },
                    "description": {
                        "type": "string",
                        "description": "Payment description (e.g., 'Order #12345 - 2 Large Pizzas')"
                    }
                },
                "required": ["amount", "card_number", "exp_month", "exp_year", "cvv", "postal_code"]
            }
        }
    ]


def get_shopify_tools() -> list:
    """
    Return OpenAI function definitions for Shopify product operations.
    AI can search products, check inventory, and create orders.
    """
    return [
        {
            "type": "function",
            "name": "search_shopify_products",
            "description": "Search for products in the Shopify store by name. Use this when customer asks about a product.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Product name or search term (e.g., 't-shirt', 'blue shoes')"
                    }
                },
                "required": ["query"]
            }
        },
        {
            "type": "function",
            "name": "check_shopify_inventory",
            "description": "Check if a product variant is in stock and get the price.",
            "parameters": {
                "type": "object",
                "properties": {
                    "variant_id": {
                        "type": "integer",
                        "description": "Shopify variant ID from search results"
                    }
                },
                "required": ["variant_id"]
            }
        },
        {
            "type": "function",
            "name": "create_shopify_order",
            "description": "Create an order in Shopify after customer confirms purchase and provides payment.",
            "parameters": {
                "type": "object",
                "properties": {
                    "customer_name": {
                        "type": "string",
                        "description": "Customer's full name"
                    },
                    "customer_email": {
                        "type": "string",
                        "description": "Customer's email address"
                    },
                    "customer_phone": {
                        "type": "string",
                        "description": "Customer's phone number"
                    },
                    "line_items": {
                        "type": "array",
                        "description": "Products being ordered",
                        "items": {
                            "type": "object",
                            "properties": {
                                "variant_id": {"type": "integer"},
                                "quantity": {"type": "integer"},
                                "price": {"type": "string"}
                            }
                        }
                    },
                    "shipping_address": {
                        "type": "object",
                        "description": "Shipping address (if applicable)",
                        "properties": {
                            "address1": {"type": "string"},
                            "city": {"type": "string"},
                            "province": {"type": "string"},
                            "zip": {"type": "string"},
                            "country": {"type": "string"}
                        }
                    }
                },
                "required": ["customer_name", "customer_email", "customer_phone", "line_items"]
            }
        }
    ]
