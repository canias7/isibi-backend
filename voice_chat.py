import os
import json
import asyncio
import websockets
from datetime import datetime

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# ISIBI Voice AI Personality for web chat
DEFAULT_VOICE_PROMPT = """You are ISIBI, a friendly AI assistant that helps businesses automate their phone calls with voice AI. 

You are speaking with someone who is interested in learning about ISIBI's voice AI platform. Your goal is to:

1. Explain how ISIBI works in simple, conversational terms
2. Highlight key features: 24/7 availability, taking orders, booking appointments, integrating with business tools
3. Be enthusiastic but not pushy
4. Answer questions clearly and concisely
5. Suggest scheduling a demo if they're interested

Keep your responses conversational and friendly. You're speaking out loud, so avoid lists, bullet points, or overly technical jargon. Speak naturally like you're having a friendly conversation.

Example topics you can discuss:
- How voice AI answers phone calls automatically
- Taking food orders, booking appointments, answering FAQs
- Integration with Google Calendar, Shopify, Square, Slack
- Simple credit-based pricing
- Setting up an AI agent in minutes
- 24/7 customer service without hiring staff

Be helpful, warm, and genuinely excited about helping businesses succeed!"""


async def handle_voice_chat(websocket, path):
    """
    WebSocket handler for voice chat with ISIBI
    Uses OpenAI Realtime API for voice-to-voice conversation
    """
    print(f"🎤 New voice chat connection from {websocket.remote_address}")
    
    # Generate session ID
    import uuid
    session_id = str(uuid.uuid4())
    
    # Get client IP
    client_ip = websocket.remote_address[0] if websocket.remote_address else "unknown"
    
    # Connect to OpenAI Realtime API
    openai_ws_url = "wss://api.openai.com/v1/realtime?model=gpt-4o-realtime-preview-2024-12-17"
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "OpenAI-Beta": "realtime=v1"
    }
    
    try:
        async with websockets.connect(openai_ws_url, extra_headers=headers) as openai_ws:
            print(f"✅ Connected to OpenAI Realtime API for session {session_id}")
            
            # Configure session
            session_config = {
                "type": "session.update",
                "session": {
                    "modalities": ["audio", "text"],
                    "instructions": DEFAULT_VOICE_PROMPT,
                    "voice": "sage",  # Friendly, professional voice
                    "input_audio_format": "pcm16",
                    "output_audio_format": "pcm16",
                    "turn_detection": {
                        "type": "server_vad",
                        "threshold": 0.5,
                        "prefix_padding_ms": 300,
                        "silence_duration_ms": 500
                    },
                    "temperature": 0.8
                }
            }
            
            await openai_ws.send(json.dumps(session_config))
            print(f"📝 Session configured for {session_id}")
            
            # Send initial greeting
            greeting = {
                "type": "response.create",
                "response": {
                    "modalities": ["audio", "text"],
                    "instructions": "Greet the user warmly and introduce yourself as ISIBI. Ask how you can help them today."
                }
            }
            await openai_ws.send(json.dumps(greeting))
            
            # Store conversation log
            conversation_log = []
            
            # Bidirectional relay
            async def relay_client_to_openai():
                """Forward audio from client to OpenAI"""
                try:
                    async for message in websocket:
                        if isinstance(message, bytes):
                            # Audio data
                            await openai_ws.send(json.dumps({
                                "type": "input_audio_buffer.append",
                                "audio": message.hex()
                            }))
                        else:
                            # Text command (e.g., end conversation)
                            data = json.loads(message)
                            if data.get("type") == "end":
                                print(f"🔚 Client ended conversation")
                                break
                except websockets.exceptions.ConnectionClosed:
                    print(f"❌ Client disconnected")
            
            async def relay_openai_to_client():
                """Forward responses from OpenAI to client"""
                try:
                    async for message in openai_ws:
                        data = json.loads(message)
                        event_type = data.get("type")
                        
                        # Forward audio responses
                        if event_type == "response.audio.delta":
                            audio_delta = data.get("delta")
                            if audio_delta:
                                # Send audio chunk to client
                                audio_bytes = bytes.fromhex(audio_delta)
                                await websocket.send(audio_bytes)
                        
                        # Log transcript
                        elif event_type == "response.audio_transcript.delta":
                            transcript = data.get("delta")
                            if transcript:
                                print(f"🤖 AI: {transcript}")
                        
                        elif event_type == "conversation.item.input_audio_transcription.completed":
                            transcript = data.get("transcript")
                            if transcript:
                                print(f"👤 User: {transcript}")
                                
                                # Save to conversation log
                                conversation_log.append({
                                    "role": "user",
                                    "content": transcript,
                                    "timestamp": datetime.now().isoformat()
                                })
                        
                        # Forward other events to client
                        await websocket.send(json.dumps(data))
                        
                except websockets.exceptions.ConnectionClosed:
                    print(f"❌ OpenAI disconnected")
            
            # Run both relays concurrently
            await asyncio.gather(
                relay_client_to_openai(),
                relay_openai_to_client()
            )
            
            # Save conversation log to database
            try:
                from db import get_conn, sql
                
                # Save session summary
                total_turns = len([msg for msg in conversation_log if msg["role"] == "user"])
                
                conn = get_conn()
                cur = conn.cursor()
                
                # Create table if doesn't exist
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS voice_chat_logs (
                        id SERIAL PRIMARY KEY,
                        session_id TEXT NOT NULL,
                        conversation_log JSONB,
                        total_turns INTEGER,
                        client_ip TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                # Insert log
                cur.execute(sql("""
                    INSERT INTO voice_chat_logs (session_id, conversation_log, total_turns, client_ip)
                    VALUES ({PH}, {PH}, {PH}, {PH})
                """), (session_id, json.dumps(conversation_log), total_turns, client_ip))
                
                conn.commit()
                conn.close()
                
                print(f"💾 Conversation logged: {total_turns} turns")
                
            except Exception as e:
                print(f"⚠️ Failed to save conversation log: {e}")
    
    except Exception as e:
        print(f"❌ Voice chat error: {e}")
        await websocket.send(json.dumps({
            "type": "error",
            "error": str(e)
        }))


async def start_voice_chat_server(port=8765):
    """
    Start WebSocket server for voice chat
    """
    print(f"🎤 Starting voice chat server on port {port}")
    
    async with websockets.serve(handle_voice_chat, "0.0.0.0", port):
        print(f"✅ Voice chat server running on ws://0.0.0.0:{port}")
        await asyncio.Future()  # Run forever


if __name__ == "__main__":
    asyncio.run(start_voice_chat_server())
