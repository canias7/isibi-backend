# Google Calendar Integration Setup

## Step 1: Create Google Cloud Project

1. Go to https://console.cloud.google.com/
2. Create a new project (or select existing)
3. Enable Google Calendar API:
   - Go to "APIs & Services" → "Library"
   - Search for "Google Calendar API"
   - Click "Enable"

## Step 2: Create OAuth Credentials

1. Go to "APIs & Services" → "Credentials"
2. Click "Create Credentials" → "OAuth client ID"
3. Configure consent screen if prompted:
   - User Type: External
   - App name: "Your App Name"
   - Add your email
   - Add scopes: `https://www.googleapis.com/auth/calendar`
4. Application type: **Web application**
5. Authorized redirect URIs:
   - Add: `https://isibi-backend.onrender.com/api/google/callback`
   - For local testing: `http://localhost:5050/api/google/callback`
6. Click "Create"
7. Copy your **Client ID** and **Client Secret**

## Step 3: Add to Render Environment Variables

Go to Render Dashboard → Your Service → Environment:

```
GOOGLE_CLIENT_ID=your_client_id_here
GOOGLE_CLIENT_SECRET=your_client_secret_here
GOOGLE_REDIRECT_URI=https://isibi-backend.onrender.com/api/google/callback
```

## Step 4: Frontend Integration

### Connect Calendar Button

```javascript
const connectCalendar = async (agentId) => {
  const token = localStorage.getItem('token');
  
  const response = await fetch(
    `https://isibi-backend.onrender.com/api/agents/${agentId}/google/auth`,
    {
      headers: {
        'Authorization': `Bearer ${token}`
      }
    }
  );
  
  const data = await response.json();
  
  // Redirect user to Google OAuth
  window.location.href = data.auth_url;
};
```

### Disconnect Calendar Button

```javascript
const disconnectCalendar = async (agentId) => {
  const token = localStorage.getItem('token');
  
  await fetch(
    `https://isibi-backend.onrender.com/api/agents/${agentId}/google/disconnect`,
    {
      method: 'DELETE',
      headers: {
        'Authorization': `Bearer ${token}`
      }
    }
  );
  
  console.log('Calendar disconnected');
};
```

## Step 5: How It Works

Once connected, the AI can:

1. **Check Availability**: "Is 2pm on Friday available?"
2. **Book Appointments**: "Book John Smith for 3pm tomorrow, phone 555-1234"
3. **List Appointments**: "What appointments do we have today?"

The AI will automatically use these functions during phone calls when calendar is connected.

## Timezone Configuration

Edit `google_calendar.py` line 257:
```python
'timeZone': 'America/New_York',  # Change to your timezone
```

Common timezones:
- `America/New_York` (EST/EDT)
- `America/Chicago` (CST/CDT)
- `America/Denver` (MST/MDT)
- `America/Los_Angeles` (PST/PDT)
