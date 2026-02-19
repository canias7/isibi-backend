# Usage Tracking & Billing System

## Overview
Automatically tracks all calls and calculates costs based on duration. Perfect for charging customers based on usage.

## How It Works

### 1. Automatic Tracking
Every call is automatically tracked:
- **Start time** - When customer calls
- **End time** - When call ends  
- **Duration** - In seconds
- **Cost** - Calculated at $0.05/minute (configurable)

### 2. Database Tables

**call_usage** - Individual call records
- user_id, agent_id
- call_sid (unique call ID)
- call_from, call_to
- duration_seconds
- cost_usd
- started_at, ended_at
- status (active/completed)

**monthly_usage** - Aggregated monthly stats
- user_id, month
- total_calls
- total_minutes
- total_cost_usd

## API Endpoints

### Get Current Month Usage
```
GET /api/usage/current
Authorization: Bearer {token}

Response:
{
  "month": "2026-02",
  "total_calls": 45,
  "total_minutes": 123.5,
  "total_cost_usd": 6.18
}
```

### Get Specific Month Usage
```
GET /api/usage/history?month=2026-01
Authorization: Bearer {token}

Response:
{
  "month": "2026-01",
  "total_calls": 38,
  "total_minutes": 98.2,
  "total_cost_usd": 4.91
}
```

### Get Call History
```
GET /api/usage/calls?limit=50
Authorization: Bearer {token}

Response:
{
  "calls": [
    {
      "id": 123,
      "agent_name": "juana",
      "call_from": "MZ...",
      "call_to": "+18449263376",
      "duration_seconds": 145,
      "cost_usd": 0.12,
      "started_at": "2026-02-18 14:30:00",
      "ended_at": "2026-02-18 14:32:25",
      "status": "completed"
    }
  ]
}
```

## Frontend Integration

### Display Current Usage
```javascript
const fetchUsage = async () => {
  const token = localStorage.getItem('token');
  
  const response = await fetch('https://isibi-backend.onrender.com/api/usage/current', {
    headers: { 'Authorization': `Bearer ${token}` }
  });
  
  const usage = await response.json();
  
  console.log(`Total Calls: ${usage.total_calls}`);
  console.log(`Total Minutes: ${usage.total_minutes}`);
  console.log(`Total Cost: $${usage.total_cost_usd}`);
};
```

### Display Call History
```javascript
const fetchCalls = async () => {
  const token = localStorage.getItem('token');
  
  const response = await fetch('https://isibi-backend.onrender.com/api/usage/calls?limit=20', {
    headers: { 'Authorization': `Bearer ${token}` }
  });
  
  const data = await response.json();
  
  data.calls.forEach(call => {
    console.log(`${call.agent_name}: ${call.duration_seconds}s - $${call.cost_usd}`);
  });
};
```

### Usage Dashboard Component Example
```jsx
import { useState, useEffect } from 'react';

export default function UsageDashboard() {
  const [usage, setUsage] = useState(null);
  const [calls, setCalls] = useState([]);
  
  useEffect(() => {
    fetchData();
  }, []);
  
  const fetchData = async () => {
    const token = localStorage.getItem('token');
    
    // Get current usage
    const usageRes = await fetch('/api/usage/current', {
      headers: { 'Authorization': `Bearer ${token}` }
    });
    setUsage(await usageRes.json());
    
    // Get recent calls
    const callsRes = await fetch('/api/usage/calls?limit=10', {
      headers: { 'Authorization': `Bearer ${token}` }
    });
    const callsData = await callsRes.json();
    setCalls(callsData.calls);
  };
  
  if (!usage) return <div>Loading...</div>;
  
  return (
    <div className="usage-dashboard">
      <div className="usage-summary">
        <h2>This Month's Usage</h2>
        <div className="stat">
          <span className="label">Total Calls</span>
          <span className="value">{usage.total_calls}</span>
        </div>
        <div className="stat">
          <span className="label">Total Minutes</span>
          <span className="value">{usage.total_minutes.toFixed(1)}</span>
        </div>
        <div className="stat">
          <span className="label">Total Cost</span>
          <span className="value">${usage.total_cost_usd.toFixed(2)}</span>
        </div>
      </div>
      
      <div className="call-history">
        <h3>Recent Calls</h3>
        <table>
          <thead>
            <tr>
              <th>Agent</th>
              <th>Duration</th>
              <th>Cost</th>
              <th>Date</th>
            </tr>
          </thead>
          <tbody>
            {calls.map(call => (
              <tr key={call.id}>
                <td>{call.agent_name}</td>
                <td>{Math.floor(call.duration_seconds / 60)}m {call.duration_seconds % 60}s</td>
                <td>${call.cost_usd.toFixed(4)}</td>
                <td>{new Date(call.started_at).toLocaleString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
```

## Pricing Configuration

### Change Price Per Minute
In `main.py`, line ~430:
```python
cost = calculate_call_cost(duration_seconds, price_per_minute=0.05)
```

Change `0.05` to your desired rate:
- $0.05/min = $3.00/hour
- $0.10/min = $6.00/hour
- $0.03/min = $1.80/hour

### Common Pricing Models

**Pay-as-you-go:**
- $0.05/minute
- No monthly fee
- Best for low-volume users

**Tiered Pricing:**
- 0-500 minutes: $0.06/min
- 500-2000 minutes: $0.04/min
- 2000+ minutes: $0.02/min

**Subscription + Overage:**
- $49/month includes 1000 minutes
- $0.05/min for additional minutes

## Billing Integration

To charge customers, integrate with:

### Stripe
```javascript
// Create invoice based on usage
const createInvoice = async (userId, month) => {
  const usage = await fetch(`/api/usage/history?month=${month}`);
  const data = await usage.json();
  
  // Create Stripe invoice
  const invoice = await stripe.invoices.create({
    customer: stripeCustomerId,
    description: `AI Voice Agent Usage - ${month}`,
    amount: Math.round(data.total_cost_usd * 100), // cents
  });
};
```

### Manual Billing
Export usage data and send invoices:
```javascript
const exportUsage = async (month) => {
  const response = await fetch(`/api/usage/history?month=${month}`);
  const usage = await response.json();
  
  // Generate invoice
  return `
    Invoice for ${month}
    Total Calls: ${usage.total_calls}
    Total Minutes: ${usage.total_minutes}
    Amount Due: $${usage.total_cost_usd}
  `;
};
```

## Next Steps

1. **Deploy** the updated backend
2. **Add usage dashboard** to your frontend (Lovable)
3. **Set your pricing** in main.py
4. **Integrate billing** (Stripe, PayPal, etc.)
5. **Monitor usage** to ensure accurate tracking

## Testing

Make a test call and check:
```bash
# View logs for tracking
# Should see:
📊 Call tracking started for user 1
📊 Call ended: 120s, Cost: $0.1000
```

Then check API:
```bash
curl -H "Authorization: Bearer {token}" \
  https://isibi-backend.onrender.com/api/usage/current
```

Perfect for charging customers accurately! 💰
