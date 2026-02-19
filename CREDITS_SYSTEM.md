# Credit-Based Billing System

## Overview
Pre-purchase credits system where customers buy credits upfront (e.g., $10) and credits are deducted with each call at 5x your cost.

## How It Works

### Credit Pricing
**Your Cost:** $0.05/minute (what you pay OpenAI/Twilio)
**Customer Pays:** $0.25/minute in credits (5x markup)
**Your Profit:** $0.20/minute

### Example Flow
1. Customer buys **$10 in credits**
2. They make a 10-minute call
3. **$2.50 deducted** from their balance ($0.25/min × 10 min)
4. Remaining balance: **$7.50**
5. Customer can make more calls until balance reaches $0

### Credit Calculation
```
10-minute call:
- Your cost: $0.50
- Credits deducted: $2.50 (shown to customer)
- Customer's new balance: $7.50
- Your profit: $2.00
```

## Database Tables

### user_credits
Stores current balance for each user:
```sql
user_id: 1
balance: 7.50          # Current credits available
total_purchased: 10.00 # Lifetime purchases
total_used: 2.50       # Lifetime usage
```

### credit_transactions
All purchases and usage:
```sql
type: "purchase"  | amount: +10.00  | balance_after: 10.00
type: "usage"     | amount: -2.50   | balance_after: 7.50
```

## API Endpoints

### Get Credit Balance
```
GET /api/credits/balance
Authorization: Bearer {token}

Response:
{
  "balance": 7.50,
  "total_purchased": 10.00,
  "total_used": 2.50
}
```

### Purchase Credits
```
POST /api/credits/purchase
Authorization: Bearer {token}
Content-Type: application/json

{
  "amount": 10.00,
  "payment_method": "stripe",
  "transaction_id": "ch_xxxxx"
}

Response:
{
  "ok": true,
  "amount_added": 10.00,
  "new_balance": 17.50
}
```

### Get Transaction History
```
GET /api/credits/transactions?limit=50
Authorization: Bearer {token}

Response:
{
  "transactions": [
    {
      "id": 1,
      "amount": 10.00,
      "type": "purchase",
      "description": "Credit purchase: $10.00",
      "balance_after": 10.00,
      "created_at": "2026-02-18 10:00:00"
    },
    {
      "id": 2,
      "amount": -2.50,
      "type": "usage",
      "description": "Call to juana (600s)",
      "balance_after": 7.50,
      "created_at": "2026-02-18 14:30:00"
    }
  ]
}
```

## Frontend Integration

### Credits Dashboard
```jsx
import { useState, useEffect } from 'react';

export default function CreditsDashboard() {
  const [credits, setCredits] = useState(null);
  const [transactions, setTransactions] = useState([]);
  
  useEffect(() => {
    fetchCredits();
    fetchTransactions();
  }, []);
  
  const fetchCredits = async () => {
    const token = localStorage.getItem('token');
    const response = await fetch('/api/credits/balance', {
      headers: { 'Authorization': `Bearer ${token}` }
    });
    setCredits(await response.json());
  };
  
  const fetchTransactions = async () => {
    const token = localStorage.getItem('token');
    const response = await fetch('/api/credits/transactions?limit=20', {
      headers: { 'Authorization': `Bearer ${token}` }
    });
    const data = await response.json();
    setTransactions(data.transactions);
  };
  
  if (!credits) return <div>Loading...</div>;
  
  const isLowBalance = credits.balance < 5;
  
  return (
    <div className="credits-dashboard">
      {/* Credit Balance Card */}
      <div className={`balance-card ${isLowBalance ? 'low-balance' : ''}`}>
        <h2>Credit Balance</h2>
        <div className="balance-amount">
          ${credits.balance.toFixed(2)}
        </div>
        
        {isLowBalance && (
          <div className="alert warning">
            ⚠️ Low balance! Add credits to keep your agents running.
          </div>
        )}
        
        <button 
          className="btn-primary"
          onClick={() => window.location.href = '/buy-credits'}
        >
          Buy More Credits
        </button>
        
        <div className="stats">
          <div className="stat">
            <span className="label">Total Purchased</span>
            <span className="value">${credits.total_purchased.toFixed(2)}</span>
          </div>
          <div className="stat">
            <span className="label">Total Used</span>
            <span className="value">${credits.total_used.toFixed(2)}</span>
          </div>
        </div>
      </div>
      
      {/* Transaction History */}
      <div className="transactions">
        <h3>Transaction History</h3>
        <table>
          <thead>
            <tr>
              <th>Date</th>
              <th>Type</th>
              <th>Amount</th>
              <th>Balance</th>
            </tr>
          </thead>
          <tbody>
            {transactions.map(tx => (
              <tr key={tx.id}>
                <td>{new Date(tx.created_at).toLocaleDateString()}</td>
                <td>
                  <span className={`badge ${tx.type}`}>
                    {tx.type === 'purchase' ? '💳 Purchase' : '📞 Call'}
                  </span>
                </td>
                <td className={tx.amount > 0 ? 'positive' : 'negative'}>
                  {tx.amount > 0 ? '+' : ''}${Math.abs(tx.amount).toFixed(2)}
                </td>
                <td>${tx.balance_after.toFixed(2)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
```

### Buy Credits Page with Stripe
```jsx
import { useState } from 'react';
import { loadStripe } from '@stripe/stripe-js';

const stripePromise = loadStripe('pk_live_xxxxx');

export default function BuyCredits() {
  const [amount, setAmount] = useState(10);
  const [loading, setLoading] = useState(false);
  
  const handlePurchase = async () => {
    setLoading(true);
    
    try {
      // 1. Create Stripe payment intent
      const stripe = await stripePromise;
      const response = await fetch('/api/create-payment-intent', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${localStorage.getItem('token')}`
        },
        body: JSON.stringify({ amount: amount * 100 }) // cents
      });
      
      const { clientSecret } = await response.json();
      
      // 2. Confirm payment
      const { error, paymentIntent } = await stripe.confirmCardPayment(clientSecret, {
        payment_method: {
          card: elements.getElement(CardElement),
        }
      });
      
      if (error) {
        alert('Payment failed: ' + error.message);
        return;
      }
      
      // 3. Add credits to account
      await fetch('/api/credits/purchase', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${localStorage.getItem('token')}`
        },
        body: JSON.stringify({
          amount: amount,
          payment_method: 'stripe',
          transaction_id: paymentIntent.id
        })
      });
      
      alert(`Successfully added $${amount} in credits!`);
      window.location.href = '/dashboard';
      
    } catch (error) {
      alert('Purchase failed: ' + error.message);
    } finally {
      setLoading(false);
    }
  };
  
  return (
    <div className="buy-credits-page">
      <h1>Buy Credits</h1>
      
      <div className="credit-packages">
        <div 
          className={`package ${amount === 10 ? 'selected' : ''}`}
          onClick={() => setAmount(10)}
        >
          <h3>$10</h3>
          <p>~40 minutes of calls</p>
        </div>
        
        <div 
          className={`package ${amount === 25 ? 'selected' : ''}`}
          onClick={() => setAmount(25)}
        >
          <h3>$25</h3>
          <p>~100 minutes of calls</p>
          <span className="badge">Popular</span>
        </div>
        
        <div 
          className={`package ${amount === 50 ? 'selected' : ''}`}
          onClick={() => setAmount(50)}
        >
          <h3>$50</h3>
          <p>~200 minutes of calls</p>
          <span className="badge">Best Value</span>
        </div>
      </div>
      
      <div className="custom-amount">
        <label>Or enter custom amount:</label>
        <input 
          type="number" 
          value={amount}
          onChange={(e) => setAmount(parseFloat(e.target.value))}
          min="5"
          step="5"
        />
      </div>
      
      <button 
        className="btn-primary"
        onClick={handlePurchase}
        disabled={loading}
      >
        {loading ? 'Processing...' : `Buy $${amount} Credits`}
      </button>
      
      <div className="info">
        <p>💰 Rate: $0.25 per minute</p>
        <p>🔄 Credits never expire</p>
        <p>🔒 Secure payment via Stripe</p>
      </div>
    </div>
  );
}
```

### Low Balance Alert
```jsx
export default function LowBalanceAlert({ balance }) {
  if (balance >= 5) return null;
  
  return (
    <div className="alert danger">
      <h3>⚠️ Low Credit Balance</h3>
      <p>You have ${balance.toFixed(2)} remaining. Your agents will stop working when you reach $0.</p>
      <button onClick={() => window.location.href = '/buy-credits'}>
        Add Credits Now
      </button>
    </div>
  );
}
```

## Automatic Call Blocking (Optional)

To block calls when balance is $0, update main.py:

```python
# In receive_from_twilio(), after loading agent:
credits = get_user_credits(owner_user_id)
if credits["balance"] <= 0:
    logger.warning(f"⚠️ User {owner_user_id} has no credits!")
    # Send low balance message and hang up
    await openai_ws.send(json.dumps({
        "type": "response.create",
        "response": {
            "modalities": ["audio", "text"],
            "instructions": "Say: I'm sorry, but your account has insufficient credits. Please add credits to continue using this service. Goodbye."
        }
    }))
    break  # End call
```

## Change Pricing

In `main.py` line ~438-439:

```python
# YOUR COST
cost = calculate_call_cost(duration_seconds, cost_per_minute=0.05)

# CUSTOMER CHARGE (change this!)
credits_to_deduct = calculate_call_revenue(duration_seconds, revenue_per_minute=0.50)  # 10x markup
```

## Testing

1. **Give user test credits:**
```bash
curl -X POST 'https://isibi-backend.onrender.com/api/credits/purchase' \
  -H 'Authorization: Bearer {token}' \
  -H 'Content-Type: application/json' \
  -d '{"amount": 10.00, "payment_method": "test"}'
```

2. **Make a call** - credits will be deducted automatically

3. **Check balance:**
```bash
curl -H "Authorization: Bearer {token}" \
  https://isibi-backend.onrender.com/api/credits/balance
```

4. **View transactions:**
```bash
curl -H "Authorization: Bearer {token}" \
  https://isibi-backend.onrender.com/api/credits/transactions
```

## Summary

✅ **Pre-purchase credits** - Customers buy upfront
✅ **Automatic deduction** - Credits removed after each call
✅ **5x markup** - $0.05 cost → $0.25 charge
✅ **Transaction history** - Full audit trail
✅ **Balance warnings** - Alert when low
✅ **Stripe integration** - Ready for payments

**Deploy and start selling credits!** 💳💰
