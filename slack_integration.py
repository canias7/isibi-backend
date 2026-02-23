import os
from datetime import datetime

# Slack will be optional - only import if available
try:
    from slack_sdk import WebClient
    from slack_sdk.errors import SlackApiError
    SLACK_AVAILABLE = True
except ImportError:
    SLACK_AVAILABLE = False
    print("⚠️ slack-sdk not installed. Run: pip install slack-sdk")

# Initialize Slack client
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
slack_client = WebClient(token=SLACK_BOT_TOKEN) if (SLACK_AVAILABLE and SLACK_BOT_TOKEN) else None


def send_slack_notification(channel: str, message: str, blocks: list = None, token: str = None):
    """
    Send a notification to Slack
    
    Args:
        channel: Slack channel ID or name (e.g., "#calls" or "C1234567890")
        message: Plain text message (fallback)
        blocks: Rich formatting blocks (optional)
        token: Optional user-specific token (overrides default)
    """
    if not SLACK_AVAILABLE:
        return {"success": False, "error": "Slack SDK not installed"}
    
    # Use provided token or default
    client = WebClient(token=token) if token else slack_client
    
    if not client:
        print("⚠️ Slack not configured - notification skipped")
        return {"success": False, "error": "Slack not configured"}
    
    try:
        response = client.chat_postMessage(
            channel=channel,
            text=message,
            blocks=blocks if blocks else None
        )
        return {"success": True, "ts": response["ts"]}
    except Exception as e:
        print(f"❌ Slack error: {str(e)}")
        return {"success": False, "error": str(e)}


def notify_new_call(agent_name: str, caller_number: str, channel: str = "#calls", token: str = None):
    """Notify when a new call starts"""
    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": "📞 New Call Started"
            }
        },
        {
            "type": "section",
            "fields": [
                {
                    "type": "mrkdwn",
                    "text": f"*Agent:*\n{agent_name}"
                },
                {
                    "type": "mrkdwn",
                    "text": f"*From:*\n{caller_number}"
                },
                {
                    "type": "mrkdwn",
                    "text": f"*Time:*\n{datetime.now().strftime('%I:%M %p')}"
                }
            ]
        }
    ]
    
    return send_slack_notification(
        channel=channel,
        message=f"📞 New call to {agent_name} from {caller_number}",
        blocks=blocks,
        token=token
    )


def notify_call_ended(agent_name: str, caller_number: str, duration: int, cost: float, channel: str = "#calls", token: str = None):
    """Notify when a call ends with summary"""
    duration_min = round(duration / 60, 1)
    
    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": "✅ Call Completed"
            }
        },
        {
            "type": "section",
            "fields": [
                {
                    "type": "mrkdwn",
                    "text": f"*Agent:*\n{agent_name}"
                },
                {
                    "type": "mrkdwn",
                    "text": f"*From:*\n{caller_number}"
                },
                {
                    "type": "mrkdwn",
                    "text": f"*Duration:*\n{duration_min} minutes"
                },
                {
                    "type": "mrkdwn",
                    "text": f"*Cost:*\n${cost:.2f}"
                }
            ]
        }
    ]
    
    return send_slack_notification(
        channel=channel,
        message=f"✅ Call completed: {agent_name} - {duration_min} min - ${cost:.2f}",
        blocks=blocks,
        token=token
    )


def notify_appointment_scheduled(agent_name: str, customer_name: str, date: str, time: str, service: str, channel: str = "#appointments", token: str = None):
    """Notify when an appointment is scheduled"""
    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": "📅 Appointment Scheduled"
            }
        },
        {
            "type": "section",
            "fields": [
                {
                    "type": "mrkdwn",
                    "text": f"*Customer:*\n{customer_name}"
                },
                {
                    "type": "mrkdwn",
                    "text": f"*Service:*\n{service}"
                },
                {
                    "type": "mrkdwn",
                    "text": f"*Date:*\n{date}"
                },
                {
                    "type": "mrkdwn",
                    "text": f"*Time:*\n{time}"
                }
            ]
        },
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": f"Scheduled by: {agent_name}"
                }
            ]
        }
    ]
    
    return send_slack_notification(
        channel=channel,
        message=f"📅 New appointment: {customer_name} - {service} - {date} at {time}",
        blocks=blocks,
        token=token
    )


def notify_order_placed(agent_name: str, customer_name: str, items: str, total: float, channel: str = "#orders", token: str = None):
    """Notify when an order is placed"""
    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": "🛍️ Order Placed"
            }
        },
        {
            "type": "section",
            "fields": [
                {
                    "type": "mrkdwn",
                    "text": f"*Customer:*\n{customer_name}"
                },
                {
                    "type": "mrkdwn",
                    "text": f"*Total:*\n${total:.2f}"
                }
            ]
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*Items:*\n{items}"
            }
        },
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": f"Taken by: {agent_name}"
                }
            ]
        }
    ]
    
    return send_slack_notification(
        channel=channel,
        message=f"🛍️ Order from {customer_name}: {items} - ${total:.2f}",
        blocks=blocks,
        token=token
    )


def notify_escalation(agent_name: str, caller_number: str, reason: str, channel: str = "#urgent", token: str = None):
    """Notify when a call needs escalation"""
    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": "⚠️ Call Escalation Needed"
            }
        },
        {
            "type": "section",
            "fields": [
                {
                    "type": "mrkdwn",
                    "text": f"*Agent:*\n{agent_name}"
                },
                {
                    "type": "mrkdwn",
                    "text": f"*From:*\n{caller_number}"
                },
                {
                    "type": "mrkdwn",
                    "text": f"*Reason:*\n{reason}"
                },
                {
                    "type": "mrkdwn",
                    "text": f"*Time:*\n{datetime.now().strftime('%I:%M %p')}"
                }
            ]
        }
    ]
    
    return send_slack_notification(
        channel=channel,
        message=f"⚠️ Escalation needed: {agent_name} - {caller_number} - {reason}",
        blocks=blocks,
        token=token
    )


def notify_low_credits(user_email: str, balance: float, channel: str = "#admin", token: str = None):
    """Notify when a user has low credits"""
    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": "💳 Low Credits Alert"
            }
        },
        {
            "type": "section",
            "fields": [
                {
                    "type": "mrkdwn",
                    "text": f"*User:*\n{user_email}"
                },
                {
                    "type": "mrkdwn",
                    "text": f"*Balance:*\n${balance:.2f}"
                }
            ]
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "⚠️ User needs to add credits to continue service"
            }
        }
    ]
    
    return send_slack_notification(
        channel=channel,
        message=f"💳 Low credits: {user_email} has ${balance:.2f}",
        blocks=blocks,
        token=token
    )
