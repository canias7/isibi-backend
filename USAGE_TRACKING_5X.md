# Usage Tracking with 5x Markup

## Overview
Tracks YOUR costs and automatically calculates what to CHARGE customers (5x your cost).

## Pricing Structure

**Your Cost:** $0.05/minute (what you pay to OpenAI/Twilio)
**Customer Price:** $0.25/minute (5x markup - what you charge)
**Your Profit:** $0.20/minute

**Example Call:**
- Duration: 10 minutes
- Your Cost: $0.50
- Customer Charged: $2.50
- Your Profit: $2.00

## API Response Format

### Get Current Month Usage
```
GET /api/usage/current

Response:
{
  "month": "2026-02",
  "total_calls": 45,
  "total_minutes": 123.5,
  "total_cost_usd": 6.18,        // What YOU paid
  "total_revenue_usd": 30.88,    // What customer pays (shown to customer)
  "total_profit_usd": 24.70      // Your profit (for your dashboard)
}
```

### Call History
```
GET /api/usage/calls

Response:
{
  "calls": [
    {
      "id": 123,
      "agent_name": "juana",
      "duration_seconds": 600,
      "cost_usd": 0.50,           // Your cost
      "revenue_usd": 2.50,        // What customer pays
      "profit_usd": 2.00,         // Your profit
      "started_at": "2026-02-18 14:30:00",
      "status": "completed"
    }
  ]
}
```

## Frontend Display

### Customer-Facing Usage Dashboard
Show customers what THEY owe (revenue):

```jsx
export default function CustomerUsage() {
  const [usage, setUsage] = useState(null);
  
  useEffect(() => {
    fetch('/api/usage/current')
      .then(r => r.json())
      .then(data => setUsage(data));
  }, []);
  
  if (!usage) return <div>Loading...</div>;
  
  return (
    <div className="usage-card">
      <h2>Your Usage This Month</h2>
      
      <div className="stat-large">
        <div className="label">Amount Due</div>
        <div className="value">${usage.total_revenue_usd.toFixed(2)}</div>
      </div>
      
      <div className="stats-grid">
        <div className="stat">
          <span className="label">Total Calls</span>
          <span className="value">{usage.total_calls}</span>
        </div>
        <div className="stat">
          <span className="label">Total Minutes</span>
          <span className="value">{usage.total_minutes.toFixed(1)}</span>
        </div>
        <div className="stat">
          <span className="label">Rate</span>
          <span className="value">$0.25/min</span>
        </div>
      </div>
      
      <button className="btn-primary">Pay Now</button>
    </div>
  );
}
```

### Admin Dashboard (Your Internal View)
Show YOUR costs and profits:

```jsx
export default function AdminUsage() {
  const [usage, setUsage] = useState(null);
  
  useEffect(() => {
    fetch('/api/usage/current')
      .then(r => r.json())
      .then(data => setUsage(data));
  }, []);
  
  if (!usage) return <div>Loading...</div>;
  
  const profitMargin = ((usage.total_profit_usd / usage.total_revenue_usd) * 100).toFixed(1);
  
  return (
    <div className="admin-dashboard">
      <h2>Business Metrics - {usage.month}</h2>
      
      <div className="metrics-grid">
        <div className="metric green">
          <div className="label">Revenue</div>
          <div className="value">${usage.total_revenue_usd.toFixed(2)}</div>
          <div className="subtext">What customers pay</div>
        </div>
        
        <div className="metric red">
          <div className="label">Costs</div>
          <div className="value">${usage.total_cost_usd.toFixed(2)}</div>
          <div className="subtext">OpenAI + Twilio</div>
        </div>
        
        <div className="metric blue">
          <div className="label">Profit</div>
          <div className="value">${usage.total_profit_usd.toFixed(2)}</div>
          <div className="subtext">{profitMargin}% margin</div>
        </div>
      </div>
      
      <div className="summary">
        <p>{usage.total_calls} calls • {usage.total_minutes.toFixed(0)} minutes</p>
      </div>
    </div>
  );
}
```

## Changing Pricing

### Update Rates in main.py (line ~434)

```python
# YOUR COST: What you pay
cost = calculate_call_cost(duration_seconds, cost_per_minute=0.05)

# CUSTOMER PRICE: What you charge (adjust this!)
revenue = calculate_call_revenue(duration_seconds, revenue_per_minute=0.25)
```

**Common Pricing Strategies:**

**5x Markup (Default):**
- Your cost: $0.05/min → Charge: $0.25/min
- Profit: $0.20/min ($12/hour)

**3x Markup (Competitive):**
- Your cost: $0.05/min → Charge: $0.15/min  
- Profit: $0.10/min ($6/hour)

**10x Markup (Premium):**
- Your cost: $0.05/min → Charge: $0.50/min
- Profit: $0.45/min ($27/hour)

### Example: Change to 10x Markup

```python
cost = calculate_call_cost(duration_seconds, cost_per_minute=0.05)
revenue = calculate_call_revenue(duration_seconds, revenue_per_minute=0.50)  # 10x
```

## Billing Integration

### Stripe Invoice Example
```javascript
const createInvoice = async (userId, month) => {
  const response = await fetch(`/api/usage/history?month=${month}`);
  const usage = await response.json();
  
  // Create Stripe invoice
  await stripe.invoices.create({
    customer: stripeCustomerId,
    collection_method: 'charge_automatically',
    auto_advance: true,
    custom_fields: [
      {
        name: 'Billing Period',
        value: usage.month
      }
    ]
  });
  
  // Add invoice item
  await stripe.invoiceItems.create({
    customer: stripeCustomerId,
    amount: Math.round(usage.total_revenue_usd * 100), // cents
    currency: 'usd',
    description: `AI Voice Agent - ${usage.total_calls} calls, ${usage.total_minutes} minutes`
  });
};
```

## Call History Table

```jsx
export default function CallHistory() {
  const [calls, setCalls] = useState([]);
  
  useEffect(() => {
    fetch('/api/usage/calls?limit=50')
      .then(r => r.json())
      .then(data => setCalls(data.calls));
  }, []);
  
  return (
    <table>
      <thead>
        <tr>
          <th>Date</th>
          <th>Agent</th>
          <th>Duration</th>
          <th>Amount</th>
        </tr>
      </thead>
      <tbody>
        {calls.map(call => (
          <tr key={call.id}>
            <td>{new Date(call.started_at).toLocaleDateString()}</td>
            <td>{call.agent_name}</td>
            <td>{Math.floor(call.duration_seconds / 60)}m {call.duration_seconds % 60}s</td>
            <td>${call.revenue_usd.toFixed(2)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
```

## Testing

Make a 2-minute test call:

**Expected Results:**
- Duration: 120 seconds (2 minutes)
- Your Cost: $0.10
- Customer Charged: $0.50
- Your Profit: $0.40

**Check logs:**
```
📊 Call ended: 120s
💰 Cost: $0.1000 | Revenue: $0.5000 | Profit: $0.4000
```

**Verify via API:**
```bash
curl -H "Authorization: Bearer {token}" \
  https://isibi-backend.onrender.com/api/usage/current
```

## Summary

✅ Tracks YOUR costs automatically
✅ Charges customers 5x your cost (configurable)
✅ Shows profit margins
✅ Ready for billing integration
✅ Separate views for customers vs. admin

**Deploy and start making profit!** 💰
