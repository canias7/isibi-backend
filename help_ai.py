import os
import openai
from datetime import datetime
from typing import List, Dict

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
openai.api_key = OPENAI_API_KEY

# Platform Help AI System Prompt
PLATFORM_HELP_PROMPT = """You are the ISIBI Platform Help Assistant. You help users navigate and use the ISIBI Voice AI platform.

You have deep knowledge about:

**ACCOUNT & CREDITS:**
- How to buy credits (Stripe payment, $10/$25/$50/$100 packages)
- Credit pricing (2x markup on actual cost, ~$0.10/min charged to users)
- How to enable auto-recharge (under $2 threshold, automatically adds $10)
- How to view credit balance and transaction history
- How to check usage and call logs

**AGENTS:**
- How to create a new AI agent
- How to configure agent settings (name, voice, system prompt)
- Available voices: alloy, ash, ballad, coral, echo, sage, shimmer, verse
- How to write effective system prompts (use the prompt generator)
- How to test an agent by calling it
- How to edit or delete agents

**PHONE NUMBERS:**
- How to purchase a Twilio phone number ($1.15/month)
- How to assign a number to an agent
- How to release/delete a phone number (no refunds)
- Area code selection for local numbers

**INTEGRATIONS:**
- Google Calendar (for scheduling appointments)
- Slack (for call notifications)
- Microsoft Teams (for call notifications)
- Square (for processing payments during calls)
- Shopify (for taking product orders)
- ElevenLabs (for custom voices - future feature)
- How to configure each integration

**NOTIFICATIONS:**
- How to set up Slack notifications (webhook or bot token)
- How to set up Teams notifications (incoming webhook)
- What notifications are sent (call start, call end, appointments, orders)

**CALL FEATURES:**
- How AI takes orders and sends SMS confirmations
- How AI books appointments via Google Calendar
- How AI processes payments via Square
- How to view call logs and transcripts
- Call summary logging

**SYSTEM PROMPTS:**
- Using the AI prompt generator
- Best practices for writing prompts
- Available prompt templates (salon, restaurant, medical, retail, etc.)
- How to structure prompts (13 sections)

**TROUBLESHOOTING:**
- Why calls aren't working (check credits, phone number assigned)
- How to fix voice quality issues (VAD settings)
- Why integrations aren't working (check API keys)
- SMS not sending (enable SMS on Twilio number)

**IMPORTANT GUIDELINES:**
1. Give clear, step-by-step instructions
2. Use bullet points for multiple steps
3. Be friendly and encouraging
4. If you don't know something specific, be honest and suggest checking documentation
5. Offer to help with related questions
6. Keep responses concise but complete
7. Use emojis sparingly for visual clarity (✅ ❌ 💡 🔧)

**EXAMPLE QUESTIONS YOU MIGHT GET:**
- "How do I buy credits?"
- "Why isn't my agent answering calls?"
- "How do I connect Google Calendar?"
- "What voices are available?"
- "How do I write a good system prompt?"
- "How much does this cost?"
- "How do I set up Slack notifications?"

Always provide actionable answers with specific steps."""


def create_help_conversation(
    user_message: str,
    conversation_history: List[Dict] = None,
    user_id: int = None
) -> Dict:
    """
    Create a help conversation with platform AI assistant
    
    Args:
        user_message: User's question
        conversation_history: Previous messages
        user_id: User ID (optional, for logging)
    
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
            {"role": "system", "content": PLATFORM_HELP_PROMPT}
        ]
        
        # Add previous messages
        if conversation_history:
            messages.extend(conversation_history)
        
        # Add new user message
        messages.append({"role": "user", "content": user_message})
        
        # Call OpenAI
        response = openai.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            temperature=0.7,  # Slightly lower for more consistent help
            max_tokens=800    # Allow longer responses for detailed help
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


def save_help_log(
    user_id: int,
    session_id: str,
    user_message: str,
    ai_response: str
) -> Dict:
    """
    Save help conversation to database
    
    Args:
        user_id: User ID
        session_id: Session identifier
        user_message: What user asked
        ai_response: What AI responded
    
    Returns:
        {"success": bool, "log_id": int}
    """
    from db import get_conn, sql
    
    try:
        conn = get_conn()
        cur = conn.cursor()
        
        # Create help_logs table if it doesn't exist
        cur.execute("""
            CREATE TABLE IF NOT EXISTS help_logs (
                id SERIAL PRIMARY KEY,
                user_id INTEGER,
                session_id TEXT NOT NULL,
                user_message TEXT NOT NULL,
                ai_response TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Insert log
        cur.execute(sql("""
            INSERT INTO help_logs (user_id, session_id, user_message, ai_response)
            VALUES ({PH}, {PH}, {PH}, {PH})
            RETURNING id
        """), (user_id, session_id, user_message, ai_response))
        
        log_id = cur.fetchone()[0]
        
        conn.commit()
        conn.close()
        
        return {"success": True, "log_id": log_id}
    
    except Exception as e:
        print(f"❌ Failed to save help log: {e}")
        return {"success": False, "error": str(e)}


def get_help_stats(user_id: int = None) -> Dict:
    """
    Get help usage statistics
    
    Args:
        user_id: Filter by user (optional)
    
    Returns:
        Statistics about help usage
    """
    from db import get_conn, sql
    
    try:
        conn = get_conn()
        cur = conn.cursor()
        
        if user_id:
            cur.execute(sql("""
                SELECT 
                    COUNT(*) as total_questions,
                    COUNT(DISTINCT session_id) as total_sessions
                FROM help_logs
                WHERE user_id = {PH}
            """), (user_id,))
        else:
            cur.execute("""
                SELECT 
                    COUNT(*) as total_questions,
                    COUNT(DISTINCT session_id) as total_sessions,
                    COUNT(DISTINCT user_id) as unique_users
                FROM help_logs
            """)
        
        row = cur.fetchone()
        conn.close()
        
        if isinstance(row, dict):
            return row
        else:
            if user_id:
                return {
                    "total_questions": row[0] if row else 0,
                    "total_sessions": row[1] if row else 0
                }
            else:
                return {
                    "total_questions": row[0] if row else 0,
                    "total_sessions": row[1] if row else 0,
                    "unique_users": row[2] if row else 0
                }
    
    except Exception as e:
        print(f"❌ Failed to get help stats: {e}")
        return {
            "total_questions": 0,
            "total_sessions": 0
        }


def get_common_questions() -> List[str]:
    """
    Get list of common help questions for quick access
    """
    return [
        "How do I buy credits?",
        "How do I create a new agent?",
        "How do I connect Google Calendar?",
        "What voices are available?",
        "How do I set up Slack notifications?",
        "Why isn't my agent answering calls?",
        "How do I write a good system prompt?",
        "How much does this cost?",
        "How do I enable auto-recharge?",
        "How do I purchase a phone number?"
    ]
