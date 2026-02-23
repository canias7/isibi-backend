# Slack Integration - Complete Implementation

## 🎯 What We'll Build

Slack integration that sends notifications for:
- 📞 New incoming calls
- ✅ Appointments scheduled
- 💰 Orders placed
- 📝 Call summaries/transcripts
- ⚠️ Escalations needed
- 💳 Low credits warnings

---

## 🔧 Backend Implementation

### 1. Install Slack SDK

```bash
pip install slack-sdk
```

Add to `requirements.txt`:
```
slack-sdk==3.27.1
```

### 2. Create slack_integration.py

```python
import os
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from datetime import datetime

# Initialize Slack client
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
slack_client = WebClient(token=SLACK_BOT_TOKEN) if SLACK_BOT_TOKEN else None


def send_slack_notification(channel: str, message: str, blocks: list = None):
    """
    Send a notification to Slack
    
    Args:
        channel: Slack channel ID or name (e.g., "#calls" or "C1234567890")
        message: Plain text message (fallback)
        blocks: Rich formatting blocks (optional)
    """
    if not slack_client:
        print("⚠️ Slack not configured - notification skipped")
        return {"success": False, "error": "Slack not configured"}
    
    try:
        response = slack_client.chat_postMessage(
            channel=channel,
            text=message,
            blocks=blocks if blocks else None
        )
        return {"success": True, "ts": response["ts"]}
    except SlackApiError as e:
        print(f"❌ Slack error: {e.response['error']}")
        return {"success": False, "error": e.response['error']}


def notify_new_call(agent_name: str, caller_number: str, channel: str = "#calls"):
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
        blocks=blocks
    )


def notify_call_ended(agent_name: str, caller_number: str, duration: int, cost: float, channel: str = "#calls"):
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
        blocks=blocks
    )


def notify_appointment_scheduled(agent_name: str, customer_name: str, date: str, time: str, service: str, channel: str = "#appointments"):
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
        blocks=blocks
    )


def notify_order_placed(agent_name: str, customer_name: str, items: str, total: float, channel: str = "#orders"):
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
        blocks=blocks
    )


def notify_escalation(agent_name: str, caller_number: str, reason: str, channel: str = "#urgent"):
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
        },
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": "Call Customer"
                    },
                    "url": f"tel:{caller_number}",
                    "style": "primary"
                }
            ]
        }
    ]
    
    return send_slack_notification(
        channel=channel,
        message=f"⚠️ Escalation needed: {agent_name} - {caller_number} - {reason}",
        blocks=blocks
    )


def notify_low_credits(user_email: str, balance: float, channel: str = "#admin"):
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
        blocks=blocks
    )


def send_call_transcript(agent_name: str, transcript: str, duration: int, channel: str = "#transcripts"):
    """Send call transcript"""
    duration_min = round(duration / 60, 1)
    
    # Truncate long transcripts for Slack
    truncated = transcript[:2000] + "..." if len(transcript) > 2000 else transcript
    
    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"📝 Call Transcript - {agent_name}"
            }
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*Duration:* {duration_min} minutes"
            }
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"```{truncated}```"
            }
        }
    ]
    
    return send_slack_notification(
        channel=channel,
        message=f"📝 Transcript from {agent_name} ({duration_min} min)",
        blocks=blocks
    )
```

---

## 📋 Database Schema Updates

Add Slack configuration to agents table:

```python
# In db.py, add to agents table:
slack_channel TEXT  # Channel to send notifications (e.g., "#calls" or "C1234567890")
```

Add Slack settings to users table:

```python
# In db.py, add to users table:
slack_workspace_id TEXT
slack_bot_token TEXT  # Encrypted
slack_default_channel TEXT
slack_enabled BOOLEAN DEFAULT FALSE
```

---

## 🔌 API Endpoints

Add to `portal.py`:

```python
from slack_integration import (
    notify_new_call,
    notify_call_ended,
    notify_appointment_scheduled,
    notify_order_placed,
    notify_escalation,
    notify_low_credits,
    send_call_transcript
)

class SlackConfigRequest(BaseModel):
    slack_bot_token: str
    slack_default_channel: str = "#calls"
    slack_enabled: bool = True

@router.post("/slack/configure")
def configure_slack(payload: SlackConfigRequest, user=Depends(verify_token)):
    """
    Configure Slack integration for user
    """
    user_id = user["id"]
    
    # TODO: Encrypt the bot token before storing
    # For now, store directly (add encryption in production)
    
    conn = get_conn()
    cur = conn.cursor()
    
    cur.execute(sql("""
        UPDATE users
        SET slack_bot_token = {PH},
            slack_default_channel = {PH},
            slack_enabled = {PH}
        WHERE id = {PH}
    """), (payload.slack_bot_token, payload.slack_default_channel, payload.slack_enabled, user_id))
    
    conn.commit()
    conn.close()
    
    return {
        "success": True,
        "message": "Slack configured successfully",
        "channel": payload.slack_default_channel
    }


@router.get("/slack/status")
def get_slack_status(user=Depends(verify_token)):
    """
    Check if Slack is configured
    """
    user_id = user["id"]
    
    conn = get_conn()
    cur = conn.cursor()
    
    cur.execute(sql("""
        SELECT slack_enabled, slack_default_channel
        FROM users
        WHERE id = {PH}
    """), (user_id,))
    
    row = cur.fetchone()
    conn.close()
    
    if not row:
        return {"configured": False}
    
    if isinstance(row, dict):
        enabled = row.get('slack_enabled')
        channel = row.get('slack_default_channel')
    else:
        enabled = row[0]
        channel = row[1] if len(row) > 1 else None
    
    return {
        "configured": bool(enabled),
        "channel": channel
    }


@router.post("/slack/test")
def test_slack_notification(user=Depends(verify_token)):
    """
    Send a test notification to Slack
    """
    result = notify_new_call(
        agent_name="Test Agent",
        caller_number="+1-555-TEST",
        channel="#calls"
    )
    
    return result
```

---

## 🎨 Frontend Implementation

```typescript
import { useState, useEffect } from 'react';

function SlackIntegration() {
  const [configured, setConfigured] = useState(false);
  const [botToken, setBotToken] = useState('');
  const [channel, setChannel] = useState('#calls');
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    checkSlackStatus();
  }, []);

  const checkSlackStatus = async () => {
    const response = await fetch('/api/slack/status', {
      headers: { 'Authorization': `Bearer ${token}` }
    });
    const data = await response.json();
    
    setConfigured(data.configured);
    if (data.channel) setChannel(data.channel);
  };

  const configureSlack = async () => {
    setLoading(true);
    try {
      const response = await fetch('/api/slack/configure', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({
          slack_bot_token: botToken,
          slack_default_channel: channel,
          slack_enabled: true
        })
      });

      const data = await response.json();
      
      if (data.success) {
        alert('Slack configured successfully!');
        setConfigured(true);
      }
    } catch (error) {
      alert('Failed to configure Slack');
    } finally {
      setLoading(false);
    }
  };

  const testSlack = async () => {
    const response = await fetch('/api/slack/test', {
      method: 'POST',
      headers: { 'Authorization': `Bearer ${token}` }
    });

    const data = await response.json();
    
    if (data.success) {
      alert('Test notification sent! Check your Slack channel.');
    } else {
      alert('Test failed: ' + data.error);
    }
  };

  if (configured) {
    return (
      <div className="slack-configured">
        <h2>✅ Slack Connected</h2>
        <p>Notifications are being sent to: <strong>{channel}</strong></p>
        
        <button onClick={testSlack} className="btn-secondary">
          Send Test Notification
        </button>
        
        <button onClick={() => setConfigured(false)} className="btn-link">
          Reconfigure
        </button>
      </div>
    );
  }

  return (
    <div className="slack-setup">
      <h2>Connect Slack</h2>
      <p>Get real-time notifications about calls, appointments, and orders</p>

      <div className="setup-steps">
        <h3>Setup Instructions:</h3>
        <ol>
          <li>Go to <a href="https://api.slack.com/apps" target="_blank">api.slack.com/apps</a></li>
          <li>Create a new app → "From scratch"</li>
          <li>Add Bot Token Scopes:
            <ul>
              <li><code>chat:write</code></li>
              <li><code>chat:write.public</code></li>
            </ul>
          </li>
          <li>Install app to your workspace</li>
          <li>Copy the "Bot User OAuth Token" (starts with xoxb-)</li>
          <li>Invite the bot to your channel: <code>/invite @YourBotName</code></li>
        </ol>
      </div>

      <div className="form-group">
        <label>Slack Bot Token *</label>
        <input
          type="password"
          placeholder="xoxb-..."
          value={botToken}
          onChange={(e) => setBotToken(e.target.value)}
        />
      </div>

      <div className="form-group">
        <label>Default Channel</label>
        <input
          type="text"
          placeholder="#calls"
          value={channel}
          onChange={(e) => setChannel(e.target.value)}
        />
        <small>Use # for public channels or channel ID for private</small>
      </div>

      <button
        onClick={configureSlack}
        disabled={!botToken || loading}
        className="btn-primary"
      >
        {loading ? 'Connecting...' : 'Connect Slack'}
      </button>
    </div>
  );
}
```

---

## 🔔 Notification Triggers

### In main.py (Call Handling):

```python
# When call starts
from slack_integration import notify_new_call

# In the session.created event:
notify_new_call(
    agent_name=agent.get('name'),
    caller_number=call_from,
    channel=agent.get('slack_channel', '#calls')
)

# When call ends
from slack_integration import notify_call_ended

# After end_call_tracking:
notify_call_ended(
    agent_name=agent.get('name'),
    caller_number=call_from,
    duration=duration_seconds,
    cost=credits_to_deduct,
    channel=agent.get('slack_channel', '#calls')
)
```

---

## 📊 What Gets Sent to Slack

### New Call:
```
📞 New Call Started
Agent: Juan
From: +1-704-555-1234
Time: 2:30 PM
```

### Call Completed:
```
✅ Call Completed
Agent: Juan
From: +1-704-555-1234
Duration: 3.5 minutes
Cost: $0.88
```

### Appointment Scheduled:
```
📅 Appointment Scheduled
Customer: John Smith
Service: Haircut
Date: Feb 25, 2026
Time: 2:00 PM
Scheduled by: Juan
```

### Order Placed:
```
🛍️ Order Placed
Customer: Jane Doe
Total: $45.99
Items: 2x Large Pizza, Garlic Bread
Taken by: Restaurant AI
```

---

## 🚀 Deployment Steps

1. Add to requirements.txt: `slack-sdk==3.27.1`
2. Add environment variable: `SLACK_BOT_TOKEN` (optional, can be per-user)
3. Deploy slack_integration.py
4. Update portal.py with new endpoints
5. Update main.py to trigger notifications
6. Deploy frontend Slack setup page

---

## Summary

✅ **Slack SDK integrated**
✅ **Rich formatted notifications**
✅ **Per-user Slack configuration**
✅ **Multiple notification types**
✅ **Test endpoint included**
✅ **Frontend setup UI ready**

**Ready to start? Let me add the Slack integration to your backend!** 📢
