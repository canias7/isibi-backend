"""
Google Calendar Integration for AI Voice Agents
Handles OAuth flow, token management, and calendar operations
"""

import os
import json
from datetime import datetime, timedelta
from typing import Optional, Dict, List
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import sqlite3
from db import get_conn

# Google OAuth Configuration
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI", "https://isibi-backend.onrender.com/api/google/callback")

SCOPES = ['https://www.googleapis.com/auth/calendar']


def get_google_oauth_url(agent_id: int, user_id: int) -> str:
    """Generate Google OAuth URL for calendar authorization"""
    
    if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
        raise ValueError("Google OAuth credentials not configured")
    
    client_config = {
        "web": {
            "client_id": GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "redirect_uris": [REDIRECT_URI],
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    }
    
    flow = Flow.from_client_config(
        client_config,
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI
    )
    
    # Store agent_id and user_id in state for callback
    state = json.dumps({"agent_id": agent_id, "user_id": user_id})
    
    authorization_url, _ = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true',
        state=state,
        prompt='consent'  # Force consent to get refresh token
    )
    
    return authorization_url


def handle_google_callback(code: str, state: str) -> Dict:
    """Handle OAuth callback and store credentials"""
    
    # Parse state
    state_data = json.loads(state)
    agent_id = state_data["agent_id"]
    user_id = state_data["user_id"]
    
    client_config = {
        "web": {
            "client_id": GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "redirect_uris": [REDIRECT_URI],
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    }
    
    flow = Flow.from_client_config(
        client_config,
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI
    )
    
    # Exchange code for tokens
    flow.fetch_token(code=code)
    credentials = flow.credentials
    
    # Store credentials in database
    creds_json = {
        "token": credentials.token,
        "refresh_token": credentials.refresh_token,
        "token_uri": credentials.token_uri,
        "client_id": credentials.client_id,
        "client_secret": credentials.client_secret,
        "scopes": credentials.scopes,
    }
    
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE agents 
        SET google_calendar_credentials = ?,
            google_calendar_id = 'primary'
        WHERE id = ? AND owner_user_id = ?
        """,
        (json.dumps(creds_json), agent_id, user_id)
    )
    conn.commit()
    conn.close()
    
    return {"ok": True, "agent_id": agent_id}


def get_calendar_credentials(agent_id: int) -> Optional[Credentials]:
    """Load Google Calendar credentials for an agent"""
    
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT google_calendar_credentials FROM agents WHERE id = ?",
        (agent_id,)
    )
    row = cur.fetchone()
    conn.close()
    
    if not row or not row[0]:
        return None
    
    creds_data = json.loads(row[0])
    
    credentials = Credentials(
        token=creds_data.get("token"),
        refresh_token=creds_data.get("refresh_token"),
        token_uri=creds_data.get("token_uri"),
        client_id=creds_data.get("client_id"),
        client_secret=creds_data.get("client_secret"),
        scopes=creds_data.get("scopes"),
    )
    
    return credentials


def disconnect_google_calendar(agent_id: int, user_id: int) -> bool:
    """Remove Google Calendar connection from agent"""
    
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE agents 
        SET google_calendar_credentials = NULL,
            google_calendar_id = NULL
        WHERE id = ? AND owner_user_id = ?
        """,
        (agent_id, user_id)
    )
    conn.commit()
    changed = cur.rowcount > 0
    conn.close()
    
    return changed


# ========== Calendar Operations (Called by AI) ==========

def check_availability(agent_id: int, date: str, time: str, duration_minutes: int = 30) -> Dict:
    """
    Check if a time slot is available in the calendar.
    
    Args:
        agent_id: Agent ID
        date: Date in YYYY-MM-DD format
        time: Time in HH:MM format (24-hour)
        duration_minutes: Appointment duration
    
    Returns:
        {"available": bool, "message": str}
    """
    
    try:
        credentials = get_calendar_credentials(agent_id)
        if not credentials:
            return {"available": False, "message": "Calendar not connected"}
        
        service = build('calendar', 'v3', credentials=credentials)
        
        # Parse datetime
        start_dt = datetime.strptime(f"{date} {time}", "%Y-%m-%d %H:%M")
        end_dt = start_dt + timedelta(minutes=duration_minutes)
        
        # Check for conflicts
        events_result = service.events().list(
            calendarId='primary',
            timeMin=start_dt.isoformat() + 'Z',
            timeMax=end_dt.isoformat() + 'Z',
            singleEvents=True,
            orderBy='startTime'
        ).execute()
        
        events = events_result.get('items', [])
        
        if events:
            return {
                "available": False,
                "message": f"Time slot not available. There are {len(events)} conflicting appointments."
            }
        else:
            return {
                "available": True,
                "message": f"Time slot is available on {date} at {time}"
            }
            
    except HttpError as e:
        return {"available": False, "message": f"Calendar error: {str(e)}"}
    except Exception as e:
        return {"available": False, "message": f"Error: {str(e)}"}


def create_appointment(
    agent_id: int,
    date: str,
    time: str,
    duration_minutes: int,
    customer_name: str,
    customer_phone: str,
    notes: str = ""
) -> Dict:
    """
    Create a calendar appointment.
    
    Args:
        agent_id: Agent ID
        date: Date in YYYY-MM-DD format
        time: Time in HH:MM format (24-hour)
        duration_minutes: Appointment duration
        customer_name: Customer's name
        customer_phone: Customer's phone
        notes: Additional notes
    
    Returns:
        {"success": bool, "message": str, "event_id": str}
    """
    
    try:
        credentials = get_calendar_credentials(agent_id)
        if not credentials:
            return {"success": False, "message": "Calendar not connected"}
        
        service = build('calendar', 'v3', credentials=credentials)
        
        # Parse datetime
        start_dt = datetime.strptime(f"{date} {time}", "%Y-%m-%d %H:%M")
        end_dt = start_dt + timedelta(minutes=duration_minutes)
        
        # Create event
        event = {
            'summary': f'Appointment with {customer_name}',
            'description': f"Phone: {customer_phone}\n\n{notes}",
            'start': {
                'dateTime': start_dt.isoformat(),
                'timeZone': 'America/New_York',  # TODO: Make configurable
            },
            'end': {
                'dateTime': end_dt.isoformat(),
                'timeZone': 'America/New_York',
            },
            'reminders': {
                'useDefault': False,
                'overrides': [
                    {'method': 'email', 'minutes': 24 * 60},
                    {'method': 'popup', 'minutes': 30},
                ],
            },
        }
        
        created_event = service.events().insert(calendarId='primary', body=event).execute()
        
        return {
            "success": True,
            "message": f"Appointment created for {date} at {time}",
            "event_id": created_event.get('id'),
            "event_link": created_event.get('htmlLink')
        }
        
    except HttpError as e:
        return {"success": False, "message": f"Calendar error: {str(e)}"}
    except Exception as e:
        return {"success": False, "message": f"Error: {str(e)}"}


def list_appointments(agent_id: int, date: str) -> Dict:
    """
    List all appointments for a specific date.
    
    Args:
        agent_id: Agent ID
        date: Date in YYYY-MM-DD format
    
    Returns:
        {"appointments": List[Dict], "count": int}
    """
    
    try:
        credentials = get_calendar_credentials(agent_id)
        if not credentials:
            return {"appointments": [], "count": 0, "message": "Calendar not connected"}
        
        service = build('calendar', 'v3', credentials=credentials)
        
        # Get start and end of day
        start_dt = datetime.strptime(date, "%Y-%m-%d")
        end_dt = start_dt + timedelta(days=1)
        
        events_result = service.events().list(
            calendarId='primary',
            timeMin=start_dt.isoformat() + 'Z',
            timeMax=end_dt.isoformat() + 'Z',
            singleEvents=True,
            orderBy='startTime'
        ).execute()
        
        events = events_result.get('items', [])
        
        appointments = []
        for event in events:
            start = event['start'].get('dateTime', event['start'].get('date'))
            appointments.append({
                "time": start,
                "summary": event.get('summary', 'No title'),
                "description": event.get('description', '')
            })
        
        return {
            "appointments": appointments,
            "count": len(appointments),
            "date": date
        }
        
    except HttpError as e:
        return {"appointments": [], "count": 0, "message": f"Error: {str(e)}"}
    except Exception as e:
        return {"appointments": [], "count": 0, "message": f"Error: {str(e)}"}
