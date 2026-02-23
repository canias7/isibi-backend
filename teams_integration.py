import os
import requests
from datetime import datetime

# Teams uses Incoming Webhooks - no SDK needed, just HTTP requests


def send_teams_notification(webhook_url: str, title: str, message: str, fields: list = None, theme_color: str = "0078D4"):
    """
    Send notification to Microsoft Teams via Incoming Webhook
    
    Args:
        webhook_url: Teams webhook URL
        title: Title of the message
        message: Main message text
        fields: List of {"name": "Field Name", "value": "Field Value"} dicts
        theme_color: Hex color code (default: Microsoft Blue)
    
    Returns:
        {"success": bool, "error": str (if failed)}
    """
    if not webhook_url:
        return {"success": False, "error": "No webhook URL provided"}
    
    # Build Teams message card (Adaptive Card format)
    card = {
        "@type": "MessageCard",
        "@context": "https://schema.org/extensions",
        "themeColor": theme_color,
        "title": title,
        "text": message
    }
    
    # Add fields (facts) if provided
    if fields:
        card["sections"] = [{
            "facts": [{"name": f["name"], "value": f["value"]} for f in fields]
        }]
    
    try:
        response = requests.post(webhook_url, json=card, timeout=10)
        
        if response.status_code == 200:
            print(f"✅ Teams notification sent: {title}")
            return {"success": True}
        else:
            print(f"❌ Teams notification failed: {response.status_code}")
            return {"success": False, "error": f"HTTP {response.status_code}"}
    
    except Exception as e:
        print(f"❌ Teams notification error: {str(e)}")
        return {"success": False, "error": str(e)}


def notify_new_call_teams(webhook_url: str, agent_name: str, caller_number: str):
    """Notify Teams when a new call starts"""
    return send_teams_notification(
        webhook_url=webhook_url,
        title="📞 New Call Started",
        message=f"Incoming call to {agent_name}",
        fields=[
            {"name": "Agent", "value": agent_name},
            {"name": "From", "value": caller_number},
            {"name": "Time", "value": datetime.now().strftime("%I:%M %p")}
        ],
        theme_color="00AA00"  # Green
    )


def notify_call_ended_teams(webhook_url: str, agent_name: str, caller_number: str, duration: int, cost: float, summary: str = None):
    """Notify Teams when a call ends with optional summary of what happened"""
    duration_min = round(duration / 60, 1)
    
    fields = [
        {"name": "Agent", "value": agent_name},
        {"name": "From", "value": caller_number},
        {"name": "Duration", "value": f"{duration_min} minutes"},
        {"name": "Cost", "value": f"${cost:.2f}"}
    ]
    
    # Add call summary if provided
    if summary:
        fields.append({"name": "📋 Call Summary", "value": summary})
    
    return send_teams_notification(
        webhook_url=webhook_url,
        title="✅ Call Completed",
        message=f"Call to {agent_name} finished",
        fields=fields,
        theme_color="0078D4"  # Microsoft Blue
    )


def notify_appointment_scheduled_teams(webhook_url: str, agent_name: str, customer_name: str, service: str, date: str, time: str):
    """Notify Teams when appointment is scheduled"""
    return send_teams_notification(
        webhook_url=webhook_url,
        title="📅 Appointment Scheduled",
        message=f"New appointment booked by {agent_name}",
        fields=[
            {"name": "Customer", "value": customer_name},
            {"name": "Service", "value": service},
            {"name": "Date", "value": date},
            {"name": "Time", "value": time},
            {"name": "Agent", "value": agent_name}
        ],
        theme_color="5B00FF"  # Purple
    )


def notify_order_placed_teams(webhook_url: str, agent_name: str, customer_name: str, items: str, total: float):
    """Notify Teams when order is placed"""
    return send_teams_notification(
        webhook_url=webhook_url,
        title="🛍️ Order Placed",
        message=f"New order taken by {agent_name}",
        fields=[
            {"name": "Customer", "value": customer_name},
            {"name": "Items", "value": items},
            {"name": "Total", "value": f"${total:.2f}"},
            {"name": "Agent", "value": agent_name}
        ],
        theme_color="FF8C00"  # Orange
    )


def notify_escalation_teams(webhook_url: str, agent_name: str, caller_number: str, reason: str):
    """Notify Teams when escalation needed"""
    return send_teams_notification(
        webhook_url=webhook_url,
        title="⚠️ Call Escalation Needed",
        message=f"Urgent: Call requires human assistance",
        fields=[
            {"name": "Agent", "value": agent_name},
            {"name": "From", "value": caller_number},
            {"name": "Reason", "value": reason},
            {"name": "Time", "value": datetime.now().strftime("%I:%M %p")}
        ],
        theme_color="FF0000"  # Red
    )


def notify_low_credits_teams(webhook_url: str, user_email: str, balance: float):
    """Notify Teams when user has low credits"""
    return send_teams_notification(
        webhook_url=webhook_url,
        title="💳 Low Credits Alert",
        message=f"User needs to add credits",
        fields=[
            {"name": "User", "value": user_email},
            {"name": "Balance", "value": f"${balance:.2f}"},
            {"name": "Status", "value": "⚠️ Action required"}
        ],
        theme_color="FFA500"  # Orange warning
    )
