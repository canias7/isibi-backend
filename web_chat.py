import os
import openai
from datetime import datetime
from typing import List, Dict

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
openai.api_key = OPENAI_API_KEY

# Default ISIBI AI personality
DEFAULT_ISIBI_PROMPT = """You are ISIBI, an AI assistant that helps businesses automate their phone calls with voice AI. You are friendly, professional, and knowledgeable about:

- Voice AI technology and how it works
- Automating customer service calls
- Taking orders, booking appointments, answering questions
- Integration with business tools (Google Calendar, Shopify, Square, Slack, Teams)
- Credit-based pricing and how it works
- Setting up AI agents for different business types

You should:
- Be enthusiastic about helping businesses save time
- Explain technical concepts in simple terms
- Suggest relevant features based on what the user asks about
- Be conversational and engaging
- Keep responses concise (2-3 sentences unless asked for more detail)

If someone asks how ISIBI works, explain that businesses can create AI voice agents that answer their phone calls 24/7, handle customer requests, and integrate with their existing tools."""


def create_chat_conversation(
    user_message: str,
    conversation_history: List[Dict] = None,
    system_prompt: str = None
) -> Dict:
    """
    Create a chat conversation with ISIBI AI
    
    Args:
        user_message: User's message
        conversation_history: Previous messages [{"role": "user/assistant", "content": "..."}]
        system_prompt: Custom system prompt (optional)
    
    Returns:
        {
            "success": bool,
            "response": str,
            "conversation_history": [...],
            "error": str (if failed)
        }
    """
    try:
        # Build conversation history
        messages = [
            {"role": "system", "content": system_prompt or DEFAULT_ISIBI_PROMPT}
        ]
        
        # Add previous messages
        if conversation_history:
            messages.extend(conversation_history)
        
        # Add new user message
        messages.append({"role": "user", "content": user_message})
        
        # Call OpenAI
        response = openai.chat.completions.create(
            model="gpt-4o-mini",  # Fast and cost-effective
            messages=messages,
            temperature=0.8,
            max_tokens=500
        )
        
        assistant_message = response.choices[0].message.content
        
        # Update conversation history
        updated_history = (conversation_history or []) + [
            {"role": "user", "content": user_message},
            {"role": "assistant", "content": assistant_message}
        ]
        
        return {
            "success": True,
            "response": assistant_message,
            "conversation_history": updated_history,
            "tokens_used": response.usage.total_tokens
        }
    
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


def save_chat_log(
    session_id: str,
    user_message: str,
    ai_response: str,
    user_ip: str = None
) -> Dict:
    """
    Save chat conversation to database
    
    Args:
        session_id: Unique session identifier
        user_message: What user said
        ai_response: What AI responded
        user_ip: User's IP address (optional)
    
    Returns:
        {"success": bool, "log_id": int}
    """
    from db import get_conn, sql
    
    try:
        conn = get_conn()
        cur = conn.cursor()
        
        # Create chat_logs table if it doesn't exist
        cur.execute("""
            CREATE TABLE IF NOT EXISTS chat_logs (
                id SERIAL PRIMARY KEY,
                session_id TEXT NOT NULL,
                user_message TEXT NOT NULL,
                ai_response TEXT NOT NULL,
                user_ip TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Insert log
        cur.execute(sql("""
            INSERT INTO chat_logs (session_id, user_message, ai_response, user_ip)
            VALUES ({PH}, {PH}, {PH}, {PH})
            RETURNING id
        """), (session_id, user_message, ai_response, user_ip))
        
        log_id = cur.fetchone()[0]
        
        conn.commit()
        conn.close()
        
        return {"success": True, "log_id": log_id}
    
    except Exception as e:
        print(f"❌ Failed to save chat log: {e}")
        return {"success": False, "error": str(e)}


def get_chat_logs(session_id: str = None, limit: int = 100) -> List[Dict]:
    """
    Get chat conversation logs
    
    Args:
        session_id: Filter by session (optional)
        limit: Max number of logs to return
    
    Returns:
        List of chat logs
    """
    from db import get_conn, sql
    
    try:
        conn = get_conn()
        cur = conn.cursor()
        
        if session_id:
            cur.execute(sql("""
                SELECT id, session_id, user_message, ai_response, user_ip, created_at
                FROM chat_logs
                WHERE session_id = {PH}
                ORDER BY created_at DESC
                LIMIT {PH}
            """), (session_id, limit))
        else:
            cur.execute(sql("""
                SELECT id, session_id, user_message, ai_response, user_ip, created_at
                FROM chat_logs
                ORDER BY created_at DESC
                LIMIT {PH}
            """), (limit,))
        
        logs = []
        for row in cur.fetchall():
            if isinstance(row, dict):
                logs.append(row)
            else:
                logs.append({
                    "id": row[0],
                    "session_id": row[1],
                    "user_message": row[2],
                    "ai_response": row[3],
                    "user_ip": row[4],
                    "created_at": row[5].isoformat() if row[5] else None
                })
        
        conn.close()
        return logs
    
    except Exception as e:
        print(f"❌ Failed to get chat logs: {e}")
        return []


def get_session_stats() -> Dict:
    """
    Get overall chat statistics
    
    Returns:
        {
            "total_conversations": int,
            "total_messages": int,
            "unique_sessions": int
        }
    """
    from db import get_conn, sql
    
    try:
        conn = get_conn()
        cur = conn.cursor()
        
        # Get stats
        cur.execute("""
            SELECT 
                COUNT(*) as total_messages,
                COUNT(DISTINCT session_id) as unique_sessions
            FROM chat_logs
        """)
        
        row = cur.fetchone()
        conn.close()
        
        if isinstance(row, dict):
            return {
                "total_messages": row.get("total_messages", 0),
                "unique_sessions": row.get("unique_sessions", 0),
                "total_conversations": row.get("unique_sessions", 0)
            }
        else:
            return {
                "total_messages": row[0] if row else 0,
                "unique_sessions": row[1] if row else 0,
                "total_conversations": row[1] if row else 0
            }
    
    except Exception as e:
        print(f"❌ Failed to get stats: {e}")
        return {
            "total_messages": 0,
            "unique_sessions": 0,
            "total_conversations": 0
        }
