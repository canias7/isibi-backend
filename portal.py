from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from typing import Optional
import stripe
import os
from datetime import datetime

from auth import verify_token
from db import (
    get_user_credits, add_credits, get_credit_transactions, deduct_credits,
    get_conn, sql, create_user, verify_user
)

# Stripe configuration
STRIPE_API_KEY = os.getenv("STRIPE_API_KEY")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")
stripe.api_key = STRIPE_API_KEY

# Twilio configuration
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")

try:
    from twilio.rest import Client as TwilioClient
    twilio_client = TwilioClient(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN) if TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN else None
except ImportError:
    twilio_client = None

router = APIRouter()


# ========== Pydantic Models ==========

class PurchaseCreditsRequest(BaseModel):
    amount: float

class PurchaseNumberRequest(BaseModel):
    area_code: Optional[str] = None
    country_code: str = "US"


# ========== Credits Endpoints ==========

@router.get("/credits/balance")
def get_credits_balance(user=Depends(verify_token)):
    """Get user's credit balance"""
    user_id = user["id"]
    credits = get_user_credits(user_id)
    return {"balance": credits["balance"]}


@router.post("/credits/purchase")
def purchase_credits(payload: PurchaseCreditsRequest, user=Depends(verify_token)):
    """
    DEPRECATED: Use Stripe payment flow instead.
    This endpoint should NOT be called directly from frontend.
    Credits are added automatically via Stripe webhook after successful payment.
    """
    raise HTTPException(
        status_code=400, 
        detail="Direct credit purchase is not allowed. Please use the Stripe payment flow via /credits/create-payment-intent"
    )


@router.get("/credits/transactions")
def get_transactions(user=Depends(verify_token), limit: int = 50):
    """Get credit transaction history"""
    user_id = user["id"]
    transactions = get_credit_transactions(user_id, limit=limit)
    return {"transactions": transactions}


@router.get("/credits/status")
def get_credits_status(user=Depends(verify_token)):
    """Get credit balance with low balance warning"""
    user_id = user["id"]
    credits = get_user_credits(user_id)
    
    # Determine status
    balance = credits["balance"]
    status = "good"
    warning = None
    
    if balance <= 0:
        status = "out"
        warning = "Your credits have run out. Add credits immediately to keep your agents working."
    elif balance < 5:
        status = "low"
        warning = "Low balance! You have less than $5 remaining. Add credits soon."
    elif balance < 10:
        status = "medium"
        warning = "Your balance is getting low. Consider adding more credits."
    
    return {
        "balance": balance,
        "total_purchased": credits["total_purchased"],
        "total_used": credits["total_used"],
        "status": status,
        "warning": warning
    }


@router.post("/credits/create-payment-intent")
def create_payment_intent(payload: PurchaseCreditsRequest, user=Depends(verify_token)):
    """Create Stripe payment intent for credit purchase"""
    user_id = user["id"]
    amount_cents = int(payload.amount * 100)  # Convert to cents
    
    try:
        # Create Stripe payment intent
        intent = stripe.PaymentIntent.create(
            amount=amount_cents,
            currency="usd",
            metadata={
                "user_id": user_id,
                "credit_amount": payload.amount
            },
            description=f"Purchase ${payload.amount} in credits"
        )
        
        return {
            "client_secret": intent.client_secret,
            "amount": payload.amount
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create payment intent: {str(e)}")


@router.post("/stripe/webhook")
async def stripe_webhook(request: Request):
    """Handle Stripe webhook events"""
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")
    
    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, STRIPE_WEBHOOK_SECRET
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Webhook error: {str(e)}")
    
    # Handle successful payment
    if event["type"] == "payment_intent.succeeded":
        payment_intent = event["data"]["object"]
        user_id = int(payment_intent["metadata"]["user_id"])
        credit_amount = float(payment_intent["metadata"]["credit_amount"])
        payment_id = payment_intent["id"]
        
        # Add credits to user's account
        add_credits(
            user_id,
            credit_amount,
            f"Credit purchase via Stripe - ${credit_amount}",
            transaction_id=payment_id
        )
        
        print(f"✅ Added ${credit_amount} credits to user {user_id} - Payment ID: {payment_id}")
    
    return {"ok": True}


# ========== Phone Number Management ==========

@router.post("/phone/search")
def search_available_numbers(payload: PurchaseNumberRequest, user=Depends(verify_token)):
    """
    Search for available Twilio numbers (BEFORE creating agent)
    """
    if not twilio_client:
        raise HTTPException(
            status_code=503, 
            detail="Twilio not configured. Please add TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN to environment variables."
        )
    
    try:
        # Search for available numbers
        search_params = {
            "limit": 10
        }
        
        if payload.area_code:
            search_params["area_code"] = payload.area_code
        
        available_numbers = twilio_client.available_phone_numbers(payload.country_code).local.list(**search_params)
        
        numbers = [
            {
                "phone_number": num.phone_number,
                "friendly_name": num.friendly_name,
                "locality": num.locality,
                "region": num.region
            }
            for num in available_numbers
        ]
        
        return {"numbers": numbers}
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to search numbers: {str(e)}")


@router.get("/phone/my-numbers")
def get_my_phone_numbers(user=Depends(verify_token)):
    """Get all phone numbers owned by the user"""
    if not twilio_client:
        raise HTTPException(status_code=503, detail="Twilio not configured")
    
    user_id = user["id"]
    
    try:
        # Get user's agents with phone numbers
        conn = get_conn()
        cur = conn.cursor()
        
        cur.execute(sql("""
            SELECT id, name, phone_number
            FROM agents
            WHERE owner_user_id = {PH} AND phone_number IS NOT NULL
        """), (user_id,))
        
        agents_with_numbers = []
        for row in cur.fetchall():
            if isinstance(row, dict):
                agents_with_numbers.append({
                    "agent_id": row['id'],
                    "agent_name": row['name'],
                    "phone_number": row['phone_number']
                })
            else:
                agents_with_numbers.append({
                    "agent_id": row[0],
                    "agent_name": row[1],
                    "phone_number": row[2]
                })
        
        conn.close()
        
        # Get actual Twilio numbers
        twilio_numbers = twilio_client.incoming_phone_numbers.list()
        
        # Match them up
        result = []
        for agent in agents_with_numbers:
            for tw_num in twilio_numbers:
                if tw_num.phone_number == agent["phone_number"]:
                    result.append({
                        "phone_number": tw_num.phone_number,
                        "friendly_name": tw_num.friendly_name,
                        "agent_id": agent["agent_id"],
                        "agent_name": agent["agent_name"],
                        "sid": tw_num.sid,
                        "monthly_cost": 1.15  # Twilio standard cost
                    })
                    break
        
        return {"numbers": result}
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get phone numbers: {str(e)}")


# ========== ADMIN ENDPOINTS ==========

from admin import (
    get_admin_dashboard_stats,
    get_all_users,
    get_recent_activity,
    get_revenue_chart_data,
    is_admin
)

def verify_admin(user=Depends(verify_token)):
    """Verify user is an admin"""
    user_id = user["id"]
    
    if not is_admin(user_id):
        raise HTTPException(status_code=403, detail="Admin access required")
    
    return user

@router.get("/admin/dashboard")
def get_admin_dashboard(user=Depends(verify_admin)):
    """Get admin dashboard statistics"""
    stats = get_admin_dashboard_stats()
    return stats


@router.get("/admin/users")
def get_admin_users(user=Depends(verify_admin), limit: int = 100, offset: int = 0):
    """Get all users with statistics"""
    users = get_all_users(limit=limit, offset=offset)
    return {"users": users, "total": len(users)}


@router.get("/admin/activity")
def get_admin_activity(user=Depends(verify_admin), limit: int = 50):
    """Get recent platform activity"""
    activity = get_recent_activity(limit=limit)
    return {"activity": activity}


@router.get("/admin/revenue-chart")
def get_admin_revenue_chart(user=Depends(verify_admin), days: int = 30):
    """Get revenue chart data"""
    chart_data = get_revenue_chart_data(days=days)
    return chart_data


@router.get("/admin/voice-chat-logs")
def get_admin_voice_chat_logs(user=Depends(verify_admin), limit: int = 50):
    """Get voice chat logs from Talk to ISIBI"""
    try:
        conn = get_conn()
        cur = conn.cursor()
        
        cur.execute(sql("""
            SELECT id, session_id, conversation_log, total_turns, client_ip, created_at
            FROM voice_chat_logs
            ORDER BY created_at DESC
            LIMIT {PH}
        """), (limit,))
        
        logs = []
        for row in cur.fetchall():
            if isinstance(row, dict):
                conversation = row.get('conversation_log')
                if isinstance(conversation, str):
                    import json
                    conversation = json.loads(conversation)
                
                logs.append({
                    "id": row['id'],
                    "session_id": row['session_id'],
                    "conversation": conversation,
                    "total_turns": row['total_turns'],
                    "client_ip": row['client_ip'],
                    "created_at": row['created_at'].isoformat() if row['created_at'] else None
                })
            else:
                conversation = row[2]
                if isinstance(conversation, str):
                    import json
                    conversation = json.loads(conversation)
                
                logs.append({
                    "id": row[0],
                    "session_id": row[1],
                    "conversation": conversation,
                    "total_turns": row[3],
                    "client_ip": row[4],
                    "created_at": row[5].isoformat() if row[5] else None
                })
        
        conn.close()
        return {"logs": logs, "total": len(logs)}
    
    except Exception as e:
        print(f"❌ Failed to get voice chat logs: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get logs: {str(e)}")


@router.post("/admin/users/{user_id}/credits")
def admin_add_credits(user_id: int, amount: float, user=Depends(verify_admin)):
    """Manually add credits to a user (admin only)"""
    try:
        add_credits(
            user_id=user_id,
            amount=amount,
            description=f"Admin credit adjustment by {user['email']}",
            transaction_id=f"ADMIN-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        )
        
        return {"success": True, "message": f"Added ${amount:.2f} to user {user_id}"}
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to add credits: {str(e)}")
