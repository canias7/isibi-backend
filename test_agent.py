import os
import json
import asyncio
import websockets
from datetime import datetime

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")


async def handle_test_agent_call(websocket, agent_id: int, user_id: int):
    """
    WebSocket handler for testing an agent via voice
    Uses OpenAI Realtime API with agent's configuration
    
    Args:
        websocket: WebSocket connection
        agent_id: Agent to test
        user_id: User testing the agent
    """
    print(f"🎤 Test call started for agent {agent_id} by user {user_id}")
    
    # Get agent configuration
    from db import get_conn, sql
    
    conn = get_conn()
    cur = conn.cursor()
    
    try:
        cur.execute(sql("""
            SELECT id, name, system_prompt, voice, owner_user_id
            FROM agents
            WHERE id = {PH} AND owner_user_id = {PH}
        """), (agent_id, user_id))
        
        agent_row = cur.fetchone()
        conn.close()
        
        if not agent_row:
            await websocket.send(json.dumps({
                "type": "error",
                "error": "Agent not found or access denied"
            }))
            return
        
        # Parse agent data
        if isinstance(agent_row, dict):
            agent_name = agent_row['name']
            system_prompt = agent_row['system_prompt']
            voice = agent_row['voice'] or 'alloy'
        else:
            agent_name = agent_row[1]
            system_prompt = agent_row[2]
            voice = agent_row[3] or 'alloy'
        
        print(f"✅ Testing agent: {agent_name} (voice: {voice})")
        
    except Exception as e:
        print(f"❌ Failed to load agent: {e}")
        await websocket.send(json.dumps({
            "type": "error",
            "error": f"Failed to load agent: {str(e)}"
        }))
        return
    
    # Connect to OpenAI Realtime API
    openai_ws_url = "wss://api.openai.com/v1/realtime?model=gpt-4o-realtime-preview-2024-12-17"
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "OpenAI-Beta": "realtime=v1"
    }
    
    try:
        async with websockets.connect(openai_ws_url, extra_headers=headers) as openai_ws:
            print(f"✅ Connected to OpenAI for test call")
            
            # Configure session with agent's settings
            session_config = {
                "type": "session.update",
                "session": {
                    "modalities": ["audio", "text"],
                    "instructions": system_prompt,
                    "voice": voice,
                    "input_audio_format": "pcm16",
                    "output_audio_format": "pcm16",
                    "turn_detection": {
                        "type": "server_vad",
                        "threshold": 0.7,
                        "prefix_padding_ms": 300,
                        "silence_duration_ms": 800
                    },
                    "temperature": 0.8
                }
            }
            
            await openai_ws.send(json.dumps(session_config))
            print(f"📝 Session configured for test call")
            
            # Send initial greeting
            greeting = {
                "type": "response.create",
                "response": {
                    "modalities": ["audio", "text"],
                    "instructions": "Greet the caller as specified in your system prompt."
                }
            }
            await openai_ws.send(json.dumps(greeting))
            
            # Store test call transcript
            test_transcript = []
            test_started = datetime.now()
            
            # Bidirectional relay
            async def relay_client_to_openai():
                """Forward audio from client to OpenAI"""
                try:
                    async for message in websocket:
                        if isinstance(message, bytes):
                            # Audio data - forward to OpenAI
                            await openai_ws.send(json.dumps({
                                "type": "input_audio_buffer.append",
                                "audio": message.hex()
                            }))
                        else:
                            # JSON command
                            data = json.loads(message)
                            if data.get("type") == "end":
                                print(f"🔚 Test call ended by user")
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
                                print(f"🤖 Agent: {transcript}")
                        
                        elif event_type == "conversation.item.input_audio_transcription.completed":
                            transcript = data.get("transcript")
                            if transcript:
                                print(f"👤 User: {transcript}")
                                
                                # Save to test transcript
                                test_transcript.append({
                                    "role": "user",
                                    "content": transcript,
                                    "timestamp": datetime.now().isoformat()
                                })
                        
                        elif event_type == "response.done":
                            # Get AI response text
                            response_data = data.get("response", {})
                            output_items = response_data.get("output", [])
                            
                            for item in output_items:
                                if item.get("type") == "message":
                                    content = item.get("content", [])
                                    for content_item in content:
                                        if content_item.get("type") == "text":
                                            test_transcript.append({
                                                "role": "assistant",
                                                "content": content_item.get("text", ""),
                                                "timestamp": datetime.now().isoformat()
                                            })
                        
                        # Forward event to client
                        await websocket.send(json.dumps(data))
                        
                except websockets.exceptions.ConnectionClosed:
                    print(f"❌ OpenAI disconnected")
            
            # Run both relays concurrently
            await asyncio.gather(
                relay_client_to_openai(),
                relay_openai_to_client()
            )
            
            # Save test call log
            test_ended = datetime.now()
            duration_seconds = (test_ended - test_started).total_seconds()
            
            try:
                conn = get_conn()
                cur = conn.cursor()
                
                # Create test_calls table if doesn't exist
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS test_calls (
                        id SERIAL PRIMARY KEY,
                        agent_id INTEGER NOT NULL,
                        user_id INTEGER NOT NULL,
                        transcript JSONB,
                        duration_seconds INTEGER,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                # Insert test call log
                cur.execute(sql("""
                    INSERT INTO test_calls (agent_id, user_id, transcript, duration_seconds)
                    VALUES ({PH}, {PH}, {PH}, {PH})
                """), (agent_id, user_id, json.dumps(test_transcript), int(duration_seconds)))
                
                conn.commit()
                conn.close()
                
                print(f"💾 Test call logged: {duration_seconds}s, {len(test_transcript)} turns")
                
            except Exception as e:
                print(f"⚠️ Failed to save test call log: {e}")
    
    except Exception as e:
        print(f"❌ Test call error: {e}")
        await websocket.send(json.dumps({
            "type": "error",
            "error": str(e)
        }))


def get_agent_test_calls(agent_id: int, user_id: int, limit: int = 10):
    """
    Get test call history for an agent
    
    Args:
        agent_id: Agent ID
        user_id: User ID (for auth)
        limit: Max number of calls to return
    
    Returns:
        List of test calls
    """
    from db import get_conn, sql
    
    try:
        conn = get_conn()
        cur = conn.cursor()
        
        cur.execute(sql("""
            SELECT id, agent_id, transcript, duration_seconds, created_at
            FROM test_calls
            WHERE agent_id = {PH} AND user_id = {PH}
            ORDER BY created_at DESC
            LIMIT {PH}
        """), (agent_id, user_id, limit))
        
        calls = []
        for row in cur.fetchall():
            if isinstance(row, dict):
                calls.append(row)
            else:
                calls.append({
                    "id": row[0],
                    "agent_id": row[1],
                    "transcript": json.loads(row[2]) if row[2] else [],
                    "duration_seconds": row[3],
                    "created_at": row[4].isoformat() if row[4] else None
                })
        
        conn.close()
        return calls
    
    except Exception as e:
        print(f"❌ Failed to get test calls: {e}")
        return []
