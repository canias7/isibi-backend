from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from auth_routes import verify_token  # your JWT verify function
from db import create_agent, list_agents, get_agent, update_agent, delete_agent, get_user_usage, get_call_history, get_user_credits, add_credits, get_credit_transactions, get_user_google_credentials, assign_google_calendar_to_agent, deduct_credits
from google_calendar import get_google_oauth_url, handle_google_callback, disconnect_google_calendar
from fastapi.responses import RedirectResponse, HTMLResponse
import os
import stripe
from twilio.rest import Client

# Stripe configuration
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")

# Twilio configuration
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
BACKEND_URL = os.getenv("BACKEND_URL", "https://isibi-backend.onrender.com")

# Initialize Twilio client only if credentials are available
twilio_client = None
if TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN:
    twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

router = APIRouter(prefix="/api", tags=["portal"])

# ---------- Models ----------

class ToolsModel(BaseModel):
    google_calendar: Optional[Dict[str, Any]] = None
    slack: Optional[Dict[str, Any]] = None

class CreateAgentRequest(BaseModel):
    # phone number section
    phone_number: Optional[str] = None
    twilio_number_sid: Optional[str] = None  # The Twilio SID of the pre-purchased number

    # assistant section
    business_name: Optional[str] = None
    assistant_name: str  # required
    first_message: Optional[str] = None
    system_prompt: Optional[str] = None
    provider: Optional[str] = None

    # voice section
    voice: Optional[str] = None

    # tools section
    tools: Optional[ToolsModel] = None
    
    # integrations
    enable_calendar: Optional[bool] = False  # If true, assign user's calendar to this agent

class PurchaseNumberRequest(BaseModel):
    area_code: Optional[str] = None  # e.g., "704", "212"
    country: Optional[str] = "US"
    contains: Optional[str] = None  # Search for numbers containing this pattern
    
class UpdateAgentRequest(BaseModel):
    phone_number: Optional[str] = None
    business_name: Optional[str] = None
    assistant_name: Optional[str] = None
    first_message: Optional[str] = None
    system_prompt: Optional[str] = None
    provider: Optional[str] = None
    voice: Optional[str] = None
    tools: Optional[ToolsModel] = None

class PurchaseCreditsRequest(BaseModel):
    amount: float
    payment_method: Optional[str] = None
    transaction_id: Optional[str] = None

class AgentOut(BaseModel):
    id: int
    assistant_name: str
    business_name: Optional[str] = None
    phone_number: Optional[str] = None
    first_message: Optional[str] = None
    system_prompt: Optional[str] = None
    provider: Optional[str] = None
    voice: Optional[str] = None
    tools: Optional[Dict[str, Any]] = None
    google_calendar_connected: Optional[bool] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


# ---------- Routes ----------

@router.get("/agents", response_model=List[AgentOut])
def api_list_agents(user=Depends(verify_token)):
    owner_user_id = user["id"]
    agents = list_agents(owner_user_id)

    # map DB keys -> API keys
    return [
        {
            "id": a["id"],
            "assistant_name": a["name"],
            "business_name": a.get("business_name"),
            "phone_number": a.get("phone_number"),
            "first_message": a.get("first_message"),
            "system_prompt": a.get("system_prompt"),
            "provider": a.get("provider"),
            "voice": a.get("voice"),
            "tools": a.get("tools"),
            "google_calendar_connected": bool(a.get("google_calendar_id")),
            "created_at": a.get("created_at"),
            "updated_at": a.get("updated_at"),
        }
        for a in agents
    ]


@router.post("/agents")
def api_create_agent(payload: CreateAgentRequest, user=Depends(verify_token)):
    owner_user_id = user["id"]

    agent_id = create_agent(
        owner_user_id=owner_user_id,
        name=payload.assistant_name,
        business_name=payload.business_name,
        phone_number=payload.phone_number,
        first_message=payload.first_message,
        system_prompt=payload.system_prompt,
        provider=payload.provider,
        voice=payload.voice,
        tools=(payload.tools.model_dump() if payload.tools else {}),
        twilio_number_sid=payload.twilio_number_sid,
    )
    
    # If a Twilio number was provided, update its friendly name
    if payload.twilio_number_sid and twilio_client:
        try:
            twilio_client.incoming_phone_numbers(payload.twilio_number_sid).update(
                friendly_name=f"{payload.assistant_name} - {payload.business_name or 'Agent'}"
            )
        except Exception as e:
            print(f"⚠️ Failed to update Twilio number friendly name: {e}")
    
    # If user wants calendar enabled, assign their credentials to this agent
    if payload.enable_calendar:
        success = assign_google_calendar_to_agent(owner_user_id, agent_id)
        if not success:
            # Calendar credentials not found, but agent was created
            return {
                "ok": True,
                "agent_id": agent_id,
                "warning": "Agent created but calendar not connected. Connect calendar first."
            }

    return {"ok": True, "agent_id": agent_id}


@router.get("/agents/{agent_id}", response_model=AgentOut)
def api_get_agent(agent_id: int, user=Depends(verify_token)):
    owner_user_id = user["id"]
    a = get_agent(owner_user_id, agent_id)
    if not a:
        raise HTTPException(status_code=404, detail="Agent not found")

    return {
        "id": a["id"],
        "assistant_name": a["name"],
        "business_name": a.get("business_name"),
        "phone_number": a.get("phone_number"),
        "first_message": a.get("first_message"),
        "system_prompt": a.get("system_prompt"),
        "provider": a.get("provider"),
        "voice": a.get("voice"),
        "tools": a.get("tools"),
        "google_calendar_connected": bool(a.get("google_calendar_id")),
        "created_at": a.get("created_at"),
        "updated_at": a.get("updated_at"),
    }


@router.patch("/agents/{agent_id}")
def api_update_agent(agent_id: int, payload: UpdateAgentRequest, user=Depends(verify_token)):
    owner_user_id = user["id"]

    changed = update_agent(
        owner_user_id,
        agent_id,
        name=payload.assistant_name,  # map UI -> DB
        business_name=payload.business_name,
        phone_number=payload.phone_number,
        first_message=payload.first_message,
        system_prompt=payload.system_prompt,
        provider=payload.provider,
        voice=payload.voice,
        tools=(payload.tools.model_dump() if payload.tools else None),
    )

    if not changed:
        return {"ok": True, "updated": False}

    return {"ok": True, "updated": True}


@router.delete("/agents/{agent_id}")
def api_delete_agent(agent_id: int, user=Depends(verify_token)):
    owner_user_id = user["id"]
    
    # Get agent before deleting to check if it has a Twilio number
    agent = get_agent(owner_user_id, agent_id)
    
    # Release Twilio number if it exists
    if agent and agent.get("twilio_number_sid") and twilio_client:
        try:
            twilio_client.incoming_phone_numbers(agent["twilio_number_sid"]).delete()
            print(f"✅ Released Twilio number {agent.get('phone_number')} for deleted agent {agent_id}")
        except Exception as e:
            print(f"⚠️ Failed to release Twilio number: {e}")
            # Continue with delete anyway
    
    deleted = delete_agent(owner_user_id, agent_id)
    
    if not deleted:
        raise HTTPException(status_code=404, detail="Agent not found or you don't have permission to delete it")
    
    return {"ok": True, "deleted": True}



# ========== Google Calendar Integration ==========

@router.get("/agents/{agent_id}/google/auth")
def google_calendar_auth(agent_id: int, user=Depends(verify_token)):
    """Start Google Calendar OAuth flow"""
    owner_user_id = user["id"]
    
    # Verify user owns this agent
    agent = get_agent(owner_user_id, agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    try:
        auth_url = get_google_oauth_url(agent_id, owner_user_id)
        return {"auth_url": auth_url}
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/google/callback")
def google_calendar_callback(code: str, state: str):
    """Handle Google OAuth callback"""
    try:
        result = handle_google_callback(code, state)
        agent_id = result['agent_id']
        
        # Return success HTML that closes itself
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Calendar Connected</title>
            <style>
                body {{
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
                    display: flex;
                    justify-content: center;
                    align-items: center;
                    height: 100vh;
                    margin: 0;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    color: white;
                }}
                .container {{
                    text-align: center;
                    padding: 40px;
                    background: rgba(255, 255, 255, 0.1);
                    border-radius: 20px;
                    backdrop-filter: blur(10px);
                }}
                .success-icon {{
                    font-size: 64px;
                    margin-bottom: 20px;
                }}
                h1 {{ margin: 0 0 10px 0; }}
                p {{ opacity: 0.9; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="success-icon">✅</div>
                <h1>Google Calendar Connected!</h1>
                <p>Your AI agent can now book appointments automatically.</p>
                <p><small>You can close this window and return to your dashboard.</small></p>
            </div>
            <script>
                // Auto-close after 3 seconds
                setTimeout(() => {{
                    window.close();
                }}, 3000);
            </script>
        </body>
        </html>
        """
        return HTMLResponse(content=html_content)
        
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"OAuth error: {str(e)}")


@router.delete("/agents/{agent_id}/google/disconnect")
def google_calendar_disconnect(agent_id: int, user=Depends(verify_token)):
    """Disconnect Google Calendar from agent"""
    owner_user_id = user["id"]
    
    disconnected = disconnect_google_calendar(agent_id, owner_user_id)
    
    if not disconnected:
        raise HTTPException(status_code=404, detail="Agent not found or calendar not connected")
    
    return {"ok": True, "disconnected": True}


# ========== User-Level Google Calendar (for agent creation flow) ==========

@router.get("/google/auth")
def google_auth_user_level(user=Depends(verify_token)):
    """
    Start Google Calendar OAuth for the user (not per-agent).
    Use this during agent creation before agent exists.
    """
    user_id = user["id"]
    
    try:
        # Use agent_id = 0 as placeholder, will be updated later
        auth_url = get_google_oauth_url(agent_id=0, user_id=user_id)
        return {"auth_url": auth_url}
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/google/status")
def google_status_user_level(user=Depends(verify_token)):
    """
    Check if user has connected Google Calendar.
    Returns the credentials that can be assigned to any agent.
    """
    user_id = user["id"]
    
    creds = get_user_google_credentials(user_id)
    
    return {
        "connected": bool(creds),
        "has_credentials": bool(creds)
    }


@router.post("/agents/{agent_id}/google/assign")
def assign_calendar_to_agent(agent_id: int, user=Depends(verify_token)):
    """
    Assign user's Google Calendar credentials to an agent.
    Use this after creating an agent to enable calendar features.
    """
    user_id = user["id"]
    
    # Verify user owns this agent
    agent = get_agent(user_id, agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    success = assign_google_calendar_to_agent(user_id, agent_id)
    
    if not success:
        raise HTTPException(status_code=400, detail="No Google credentials found. Connect calendar first.")
    
    return {"ok": True, "assigned": True}


# ========== Usage & Billing Endpoints ==========

@router.get("/usage/current")
def get_current_usage(user=Depends(verify_token)):
    """Get current month's usage for the logged-in user"""
    user_id = user["id"]
    usage = get_user_usage(user_id)
    return usage


@router.get("/usage/history")
def get_usage_history(user=Depends(verify_token), month: Optional[str] = None):
    """Get usage for a specific month (YYYY-MM format)"""
    user_id = user["id"]
    usage = get_user_usage(user_id, month=month)
    return usage


@router.get("/usage/calls")
def get_calls(user=Depends(verify_token), limit: int = 50):
    """Get recent call history"""
    user_id = user["id"]
    calls = get_call_history(user_id, limit=limit)
    return {"calls": calls}


# ========== Credits System Endpoints ==========

@router.get("/credits/balance")
def get_credits_balance(user=Depends(verify_token)):
    """Get user's current credit balance"""
    user_id = user["id"]
    credits = get_user_credits(user_id)
    return credits


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
        raise HTTPException(status_code=400, detail=f"Payment failed: {str(e)}")


@router.post("/credits/webhook")
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
        
        # Add credits to user's account
        add_credits(
            user_id,
            credit_amount,
            f"Credit purchase via Stripe - ${credit_amount} (Transaction: {payment_intent['id']})"
        )
        
        print(f"✅ Added ${credit_amount} credits to user {user_id}")
    
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
        
        if payload.contains:
            search_params["contains"] = payload.contains
        
        available_numbers = twilio_client.available_phone_numbers(payload.country).local.list(**search_params)
        
        results = [
            {
                "phone_number": num.phone_number,
                "friendly_name": num.friendly_name,
                "locality": num.locality,
                "region": num.region,
                "monthly_cost": 1.15  # Twilio's base cost
            }
            for num in available_numbers
        ]
        
        return {
            "available_numbers": results,
            "monthly_cost": 1.15  # What customer pays (Twilio's cost, no markup)
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")


@router.post("/phone/purchase")
def purchase_phone_number(payload: PurchaseNumberRequest, user=Depends(verify_token)):
    """
    Purchase a Twilio phone number (BEFORE creating agent)
    Returns the number so it can be used when creating the agent
    
    IMPORTANT: Immediately deducts $1.15 from customer's credits
    """
    if not twilio_client:
        raise HTTPException(status_code=503, detail="Twilio not configured")
    
    user_id = user["id"]
    
    # Check if user has enough credits BEFORE purchasing
    credits = get_user_credits(user_id)
    if credits["balance"] < 1.15:
        raise HTTPException(
            status_code=402,  # Payment Required
            detail=f"Insufficient credits. You have ${credits['balance']:.2f}, need $1.15. Please add credits first."
        )
    
    try:
        # Search for available numbers
        search_params = {"limit": 1}
        
        if payload.area_code:
            search_params["area_code"] = payload.area_code
        
        if payload.contains:
            search_params["contains"] = payload.contains
        
        available_numbers = twilio_client.available_phone_numbers(payload.country).local.list(**search_params)
        
        if not available_numbers:
            raise HTTPException(status_code=404, detail="No numbers available with those criteria")
        
        # Purchase the number from Twilio
        purchased_number = twilio_client.incoming_phone_numbers.create(
            phone_number=available_numbers[0].phone_number,
            voice_url=f"{BACKEND_URL}/incoming-call",
            voice_method="POST",
            friendly_name=f"User {user_id} - Reserved"  # Mark as reserved until agent is created
        )
        
        # Deduct $1.15 from customer's credits immediately
        print(f"💰 Attempting to deduct $1.15 from user {user_id}")
        deduct_result = deduct_credits(
            user_id=user_id,
            amount=1.15,
            description=f"Phone number purchase: {purchased_number.phone_number}"
        )
        print(f"💰 Deduct result: {deduct_result}")
        
        if not deduct_result["success"]:
            # If deduction fails, release the number we just purchased
            print(f"❌ Credit deduction failed: {deduct_result}")
            try:
                twilio_client.incoming_phone_numbers(purchased_number.sid).delete()
            except:
                pass  # Best effort cleanup
            
            raise HTTPException(
                status_code=500,
                detail=f"Credit deduction failed: {deduct_result.get('error')}"
            )
        
        print(f"✅ Successfully deducted $1.15, new balance: ${deduct_result['balance']}")
        
        return {
            "success": True,
            "phone_number": purchased_number.phone_number,
            "twilio_sid": purchased_number.sid,
            "friendly_name": purchased_number.friendly_name,
            "monthly_cost": 1.15,
            "charged_now": 1.15,
            "new_balance": deduct_result["balance"],
            "message": f"Phone number {purchased_number.phone_number} purchased! $1.15 deducted from your credits. New balance: ${deduct_result['balance']:.2f}"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Purchase failed: {str(e)}")


@router.post("/phone/release/{twilio_sid}")
def release_phone_number_by_sid(twilio_sid: str, user=Depends(verify_token)):
    """
    Release a Twilio number that was purchased but not used
    (In case user changes their mind before creating agent)
    
    NOTE: No refund given - Twilio doesn't refund us either
    
    Use the twilio_sid from the purchase response or my-numbers list
    """
    if not twilio_client:
        raise HTTPException(status_code=503, detail="Twilio not configured")
    
    user_id = user["id"]
    
    try:
        # Verify this number belongs to the user before deleting
        number = twilio_client.incoming_phone_numbers(twilio_sid).fetch()
        
        # Check if it's the user's number (by friendly name)
        if not (number.friendly_name and f"User {user_id}" in number.friendly_name):
            raise HTTPException(status_code=403, detail="You don't own this phone number")
        
        phone_number = number.phone_number
        
        # Release the Twilio number (no refund - Twilio doesn't refund us)
        twilio_client.incoming_phone_numbers(twilio_sid).delete()
        
        return {
            "success": True,
            "message": f"Phone number {phone_number} released successfully.",
            "phone_number": phone_number
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Release failed: {str(e)}")


@router.delete("/phone/release")
def release_phone_number_by_number(phone_number: str, user=Depends(verify_token)):
    """
    Release a phone number by its phone number (e.g., +17045551234)
    Alternative to using twilio_sid
    
    NOTE: No refund given - Twilio doesn't refund us either
    """
    if not twilio_client:
        raise HTTPException(status_code=503, detail="Twilio not configured")
    
    user_id = user["id"]
    
    try:
        # Find all numbers belonging to this user
        all_numbers = twilio_client.incoming_phone_numbers.list()
        
        matching_number = None
        for num in all_numbers:
            if num.phone_number == phone_number and f"User {user_id}" in (num.friendly_name or ""):
                matching_number = num
                break
        
        if not matching_number:
            raise HTTPException(status_code=404, detail="Phone number not found or doesn't belong to you")
        
        # Release it (no refund - Twilio doesn't refund us)
        twilio_client.incoming_phone_numbers(matching_number.sid).delete()
        
        return {
            "success": True,
            "message": f"Phone number {phone_number} released successfully.",
            "phone_number": phone_number
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Release failed: {str(e)}")


@router.get("/phone/my-numbers")
def get_my_purchased_numbers(user=Depends(verify_token)):
    """
    Get all phone numbers purchased by this user (from Twilio)
    Useful to show numbers that are available to assign to agents
    """
    if not twilio_client:
        raise HTTPException(status_code=503, detail="Twilio not configured")
    
    user_id = user["id"]
    
    try:
        # Get all numbers
        all_numbers = twilio_client.incoming_phone_numbers.list()
        
        # Filter to user's numbers (those with their user_id in friendly_name)
        user_numbers = [
            {
                "phone_number": num.phone_number,
                "twilio_sid": num.sid,
                "friendly_name": num.friendly_name,
                "monthly_cost": 1.15  # Twilio's cost, no markup
            }
            for num in all_numbers
            if f"User {user_id}" in (num.friendly_name or "")
        ]
        
        return {
            "numbers": user_numbers,
            "count": len(user_numbers)
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch numbers: {str(e)}")


@router.delete("/agents/{agent_id}/phone/release")
def release_agent_phone_number(agent_id: int, user=Depends(verify_token)):
    """
    Release the Twilio number from an agent
    (Keeps the number in Twilio, just removes from agent)
    """
    if not twilio_client:
        raise HTTPException(status_code=503, detail="Twilio not configured")
    
    user_id = user["id"]
    agent = get_agent(user_id, agent_id)
    
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    if not agent.get("twilio_number_sid"):
        raise HTTPException(status_code=404, detail="Agent has no phone number")
    
    try:
        # Just clear from agent record, keep number in Twilio
        update_agent(user_id, agent_id, phone_number=None, twilio_number_sid=None)
        
        # Update friendly name to show it's available again
        twilio_client.incoming_phone_numbers(agent["twilio_number_sid"]).update(
            friendly_name=f"User {user_id} - Available"
        )
        
        return {
            "success": True,
            "message": "Phone number removed from agent (still in your account)"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Release failed: {str(e)}")


@router.get("/agents/{agent_id}/phone/status")
def get_phone_number_status(agent_id: int, user=Depends(verify_token)):
    """
    Get phone number status for an agent
    """
    user_id = user["id"]
    agent = get_agent(user_id, agent_id)
    
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    return {
        "has_number": bool(agent.get("phone_number")),
        "phone_number": agent.get("phone_number"),
        "twilio_sid": agent.get("twilio_number_sid"),
        "monthly_cost": 1.15 if agent.get("phone_number") else 0.00
    }


# ========== Call Detail Breakdown ==========

@router.get("/usage/call-details/{call_id}")
def get_call_details(call_id: int, user=Depends(verify_token)):
    """
    Get detailed cost breakdown for a specific call
    Shows what customer was charged for each service provider
    """
    user_id = user["id"]
    
    from db import get_conn, sql
    conn = get_conn()
    cur = conn.cursor()
    
    # Get call details
    cur.execute(sql("""
        SELECT 
            cu.*,
            a.name as agent_name,
            a.provider as ai_provider
        FROM call_usage cu
        LEFT JOIN agents a ON cu.agent_id = a.id
        WHERE cu.id = {PH} AND cu.user_id = {PH}
    """), (call_id, user_id))
    
    row = cur.fetchone()
    conn.close()
    
    if not row:
        raise HTTPException(status_code=404, detail="Call not found")
    
    # Convert to dict
    call = dict(row)
    
    # Get values
    duration_minutes = round(call.get("duration_seconds", 0) / 60.0, 2)
    total_revenue = call.get("revenue_usd", 0) or 0
    ai_provider = call.get("ai_provider") or "OpenAI"
    
    # Calculate breakdown
    # Twilio phone cost: $0.0085/min (your cost) * 5 (markup) = $0.0425/min customer pays
    twilio_cost = duration_minutes * 0.0425
    
    # OpenAI cost: remainder
    openai_cost = total_revenue - twilio_cost
    
    # Build simple breakdown
    breakdown = {
        "call_id": call_id,
        "agent_name": call.get("agent_name"),
        "call_sid": call.get("call_sid"),
        "duration_seconds": call.get("duration_seconds", 0),
        "duration_minutes": duration_minutes,
        "started_at": str(call.get("started_at")),
        "ended_at": str(call.get("ended_at")),
        
        "total_charged": round(total_revenue, 2),
        
        "breakdown": [
            {
                "provider": ai_provider,
                "description": "AI voice processing (speech recognition, voice synthesis, conversation)",
                "cost": round(openai_cost, 4),
                "percentage": round((openai_cost / total_revenue * 100) if total_revenue > 0 else 0, 1)
            },
            {
                "provider": "Twilio",
                "description": "Phone line service",
                "cost": round(twilio_cost, 4),
                "percentage": round((twilio_cost / total_revenue * 100) if total_revenue > 0 else 0, 1)
            }
        ],
        
        "summary": {
            "ai_service": round(openai_cost, 2),
            "phone_service": round(twilio_cost, 2),
            "total": round(total_revenue, 2)
        }
    }
    
    return breakdown


# ========== AI Prompt Generator ==========

class GeneratePromptRequest(BaseModel):
    business_name: str
    business_type: Optional[str] = "general"
    services: Optional[str] = None
    hours: Optional[str] = None
    phone_number: Optional[str] = None
    address: Optional[str] = None

@router.post("/agents/generate-prompt")
def generate_ai_prompt(payload: GeneratePromptRequest, user=Depends(verify_token)):
    """
    Generate a complete structured system prompt with 12 sections
    """
    business_name = payload.business_name
    business_type = payload.business_type or "general"
    
    # Role templates
    role_templates = {
        "salon": "professional receptionist at a barbershop/salon",
        "restaurant": "friendly host at a restaurant",
        "medical": "professional medical receptionist",
        "retail": "helpful customer service representative",
        "professional": "professional office assistant",
        "general": "professional customer service representative"
    }
    
    # Service templates
    service_templates = {
        "salon": "haircuts, styling, coloring, treatments",
        "restaurant": "dining reservations, takeout orders, catering",
        "medical": "appointment scheduling, prescription refills, general inquiries",
        "retail": "product information, orders, returns, support",
        "professional": "consultations, appointments, general inquiries",
        "general": "inquiries, appointments, and general assistance"
    }
    
    # Goal templates - more versatile
    goal_templates = {
        "salon": "Schedule appointments efficiently, answer questions about services, and handle cancellations/rescheduling",
        "restaurant": "Take food orders, make reservations, answer menu questions, provide hours and location info, and handle delivery/pickup requests",
        "medical": "Schedule appointments, handle prescription requests, triage urgent matters, and provide general office information",
        "retail": "Take orders over the phone, answer product questions, check inventory, process returns, and provide shipping information",
        "professional": "Schedule consultations, answer service questions, collect client information, and coordinate meetings",
        "general": "Assist customers with their requests, provide information, take orders or bookings, and ensure excellent service"
    }
    
    # Required info templates - varies by business type
    required_info_templates = {
        "salon": """**When Scheduling Appointments, Always Collect:**

1. **Customer's Full Name**
2. **Phone Number** (for confirmation/callback)
3. **Preferred Date & Time**
4. **Type of Service** requested
5. **Special Requirements** (if any)

**Important:** Confirm all details before finalizing the appointment.""",
        
        "restaurant": """**When Taking Orders, Always Collect:**

1. **Customer's Name**
2. **Phone Number** (for order confirmation)
3. **Order Details** (items, quantities, special requests)
4. **Calculate Total:**
   - Subtotal (sum of all items)
   - Tax (calculate based on local tax rate - typically 7-10%)
   - Delivery fee (if applicable, typically $3-5)
   - **Final Total** (subtotal + tax + delivery fee)
5. **Pickup or Delivery** preference
6. **Delivery Address** (if delivery)
7. **Preferred Time** for pickup/delivery
8. **Payment Method** - Ask: "Will this be cash or card?"
9. **If Paying by Card:**
   - Card Number (16 digits)
   - Expiration Date (MM/YY)
   - CVV (3-digit security code)
   - Billing ZIP Code

**When Making Reservations, Collect:**

1. **Customer's Name**
2. **Phone Number**
3. **Party Size** (number of people)
4. **Date & Time** preference
5. **Special Requests** (outdoor seating, high chair, etc.)

**Important:** 
- Always break down costs: "Your subtotal is $22.00, plus $1.98 tax and $3.00 delivery, for a total of $26.98"
- Repeat the complete order details for confirmation
- Confirm total amount before collecting card info
- Read back card number for verification
- Reassure customer about secure payment processing""",
        
        "medical": """**When Scheduling Appointments, Always Collect:**

1. **Patient's Full Name**
2. **Date of Birth**
3. **Phone Number**
4. **Reason for Visit**
5. **Preferred Date & Time**
6. **Insurance Information** (if new patient)

**Important:** Confirm all details and note any urgent symptoms.""",
        
        "retail": """**When Taking Orders, Always Collect:**

1. **Customer's Name**
2. **Phone Number**
3. **Email Address** (for order confirmation)
4. **Product Details** (item name, size, color, quantity)
5. **Shipping Address** (if applicable)
6. **Calculate Total:**
   - Product price
   - Shipping cost (if applicable)
   - Tax (calculate based on shipping state tax rate - typically 5-10%)
   - **Final Total**
7. **Payment Method** - Ask: "How would you like to pay for this?"
8. **If Paying by Card:**
   - Card Number (16 digits)
   - Expiration Date (MM/YY)
   - CVV (3-digit security code)
   - Billing ZIP Code
   - Cardholder Name

**When Answering Product Questions:**
• Provide accurate inventory status
• Explain product features clearly
• Suggest alternatives if item unavailable

**Important:** 
- Break down costs: "The shoes are $89.99, plus $8.00 shipping and $7.84 tax, for a total of $105.83"
- Confirm order details and total amount
- Verify card information by reading it back
- Provide order number and estimated delivery date
- Reassure customer about secure payment processing""",
        
        "professional": """**When Scheduling Consultations, Always Collect:**

1. **Client's Full Name**
2. **Phone Number** and **Email**
3. **Preferred Date & Time**
4. **Nature of Consultation**
5. **Any Preparation Needed**

**Important:** Confirm meeting details and send calendar invite if possible.""",
        
        "general": """**When Assisting Customers, Collect Relevant Information:**

1. **Customer's Name**
2. **Contact Information** (phone and/or email)
3. **Specific Request** details
4. **Preferred Date/Time** (if scheduling)
5. **Any Special Requirements**

**Important:** Adapt based on the customer's needs - appointments, orders, inquiries, etc."""
    }
    
    # Business-specific examples
    examples_by_type = {
        "salon": """**Common Interactions:**

• Customer calls to book a haircut → Schedule appointment, collect required info
• Customer asks about pricing → Provide service pricing or offer to connect with staff
• Customer wants to reschedule → Get current appointment, offer new times
• Customer asks what services you offer → List available services clearly""",
        
        "restaurant": """**Common Interactions:**

• Customer calls to place a pickup order → Take full order details, calculate total, collect payment card info, confirm order
• Customer wants to make a reservation → Collect party size, date/time, contact info
• Customer asks about menu items → Answer questions about ingredients, preparation, pricing
• Customer wants delivery → Get delivery address, take order, collect payment, confirm delivery time
• Customer asks about hours or location → Provide accurate information

**Example Order Flow (Pickup):**
1. Take order: "I'll have a large pepperoni pizza and garlic bread"
2. Calculate and announce total: "That's a large pepperoni pizza at $18.00 and garlic bread at $4.50. Your subtotal is $22.50, plus $2.03 tax, for a total of $24.53"
3. Ask for payment: "How would you like to pay for this? Cash or card?"
4. If card, collect: "I'll need your card number, expiration date, CVV, and billing ZIP code"
5. Verify: "Let me read that back - card ending in 1234, expires 05/27?"
6. Confirm: "Perfect! Your total of $24.53 has been processed. Your order will be ready for pickup in 20 minutes"

**Example Order Flow (Delivery):**
1. Take order: "I'd like a large cheese pizza delivered"
2. Get address: "What's your delivery address?"
3. Calculate with delivery fee: "That's a large cheese pizza at $16.00. Your subtotal is $16.00, plus $1.44 tax and $4.00 delivery fee, for a total of $21.44"
4. Collect payment and confirm: "I'll need your card information... Perfect! Your order will be delivered to [address] in 35-45 minutes" """,
        
        "medical": """**Common Interactions:**

• Patient calls to schedule appointment → Collect patient info, reason for visit, schedule appropriately
• Patient needs prescription refill → Get patient name, medication details, forward to appropriate staff
• Patient has urgent symptoms → Triage urgency, connect to nurse or doctor immediately if needed
• New patient calling → Collect full patient information, explain new patient process""",
        
        "retail": """**Common Interactions:**

• Customer wants to buy a product → Take order details, calculate total, collect payment card info, confirm order
• Customer asks if item is in stock → Check inventory or offer to connect with staff
• Customer wants to return item → Collect order details, explain return policy, assist with process
• Customer has product questions → Provide detailed information, suggest alternatives if needed

**Example Order Flow:**
1. Identify product: "I'd like to order the blue running shoes in size 10"
2. Confirm availability and price: "Great! We have those in stock. They're $89.99"
3. Collect shipping: "What's your shipping address?"
4. Calculate total with tax: "The shoes are $89.99, standard shipping is $8.00, and tax is $7.84 based on your state. Your total is $105.83"
5. Ask for payment: "How would you like to pay?"
6. Collect card info: "I'll need your card number, expiration, CVV, and billing ZIP"
7. Verify and confirm: "Perfect! Your order #12345 totaling $105.83 has been processed. It will arrive in 5-7 business days" """,
        
        "professional": """**Common Interactions:**

• Client wants to schedule consultation → Collect contact info, understand their needs, schedule meeting
• Client asks about services → Explain what you offer, pricing structure, process
• Client wants to reschedule → Get current appointment, offer alternatives
• New client inquiry → Gather information, explain how you work, schedule initial consultation""",
        
        "general": """**Common Interactions:**

• Customer needs to schedule/book something → Collect necessary details, confirm availability
• Customer wants information → Provide accurate answers, offer to connect with staff if needed
• Customer wants to place order → Take complete order details, confirm everything
• Customer has a question → Answer clearly, escalate if beyond your knowledge"""
    }
    
    examples = examples_by_type.get(business_type, examples_by_type["general"])
    
    # Get values for templates
    role = role_templates.get(business_type, role_templates["general"])
    services = payload.services or service_templates.get(business_type, service_templates["general"])
    goals = goal_templates.get(business_type, goal_templates["general"])
    required_info = required_info_templates.get(business_type, required_info_templates["general"])
    
    # Format business info cleanly
    business_info_lines = [f"**Business Name:** {business_name}"]
    if payload.phone_number:
        business_info_lines.append(f"**Phone:** {payload.phone_number}")
    if payload.address:
        business_info_lines.append(f"**Location:** {payload.address}")
    if payload.hours:
        business_info_lines.append(f"**Hours:** {payload.hours}")
    else:
        business_info_lines.append(f"**Hours:** Monday-Friday 9am-6pm, Saturday 10am-4pm")
    
    business_info = "\n".join(business_info_lines)
    
    # Build after-hours section
    if payload.hours:
        after_hours_header = f"**If Called Outside Business Hours ({payload.hours}):**"
        after_hours_hours = f"Our hours are {payload.hours}."
    else:
        after_hours_header = "**If Called Outside Regular Business Hours:**"
        after_hours_hours = ""
    
    after_hours_message = f'''> "Thank you for calling {business_name}. You've reached us outside of our normal business hours. {after_hours_hours}
>
> I can still help you with:
> • Scheduling an appointment for when we're open
> • Answering general questions about our services  
> • Taking a message for our team
>
> How would you like to proceed?"'''
    
    prompt = f"""# SYSTEM PROMPT FOR {business_name.upper()}


## CRITICAL INSTRUCTION
**When a call connects, IMMEDIATELY greet the caller using the greeting in Section 2. Do not wait for the caller to speak first. Start every call with the greeting.**


## 1. ROLE

You are a **{role}**.

**Your Primary Responsibilities:**
• Handle incoming phone calls professionally and efficiently
• Provide excellent customer service
• Manage appointments and inquiries
• Represent {business_name} with warmth and professionalism


## 2. GREETING

**IMPORTANT: This is the FIRST thing you say when the call connects. Say this immediately without waiting for the caller to speak first.**

**Initial Call Greeting (say this first):**
> "Thank you for calling {business_name}! This is your AI assistant. How may I help you today?"

**Returning Caller Greeting (if they provide their name):**
> "Welcome back to {business_name}, [Name]! How can I assist you today?"


## 3. TONE & COMMUNICATION STYLE

Maintain the following communication standards:

• **Professional** yet friendly and approachable
• **Patient** and understanding with all callers
• **Clear** and concise in your explanations
• **Warm** and welcoming in your demeanor
• **Helpful** and solution-oriented in your approach
• **Adaptive** - adjust formality based on the caller's tone


## 4. SERVICES

**{business_name} offers the following services:**

{services}

**When Discussing Services:**
• Provide clear, accurate information
• Explain options when relevant
• Suggest appropriate services based on customer needs
• **Never** make up information about services not listed


## 5. GOALS & OBJECTIVES

**Your Primary Goals:**

• {goals}
• Provide accurate information about services and pricing
• Collect necessary information for appointments
• Create positive customer experiences
• Handle objections professionally
• Route complex issues to appropriate staff members


## 6. REQUIRED INFORMATION

{required_info}


## 7. BUSINESS INFORMATION

{business_info}


## 8. COMMON INTERACTIONS

{examples}


## 9. FAQ HANDLING RULES

**Common Questions & How to Handle Them:**

### Pricing Inquiries
• If you have specific pricing information, provide it clearly
• If pricing varies by service, explain:
  > "Pricing depends on the specific service. I can connect you with our team for an accurate quote."

### Availability Questions
• Check calendar if tool is available
• If unsure, respond with:
  > "Let me check our availability. What dates work best for you?"

### Location & Directions
• Provide the address if available
• Offer to text or email directions if needed

### Service Details
• Explain available services clearly
• Recommend based on customer needs
• **Never** invent or assume services not explicitly listed

### Cancellation & Rescheduling
• Be understanding and helpful
• Collect current appointment details
• Offer alternative times that work for the customer


## 10. ESCALATION PROTOCOL

**Transfer to a Human Representative When:**

• Customer is upset, frustrated, or angry
• Complex technical issues arise
• Pricing negotiations are needed
• Emergency or urgent medical matters occur (if medical office)
• You lack the information the customer needs
• Customer explicitly requests to speak with a person
• Situation is beyond your capabilities

**Escalation Script:**
> "I understand this requires additional assistance. Let me connect you with the appropriate team member who can better help you with this."


## 11. AFTER-HOURS PROTOCOL

{after_hours_header}

{after_hours_message}


## 12. CONSTRAINTS & LIMITATIONS

**You MUST:**
• Always be honest about your capabilities as an AI
• Confirm all important details (dates, times, names, orders)
• Collect required information before finalizing anything
• Maintain caller privacy and confidentiality
• Be transparent when you don't have information
• **When collecting payment card information:**
  - Speak clearly and slowly
  - Read back the card number for verification
  - Reassure customer about secure payment processing
  - Confirm the total amount before collecting payment details

**You MUST NOT:**
• Make up services, prices, or policies
• Make medical diagnoses (if applicable)
• Guarantee specific outcomes
• Share other customers' information
• Pretend to be a human employee
• Make promises you cannot keep
• Be rude, dismissive, or rush the caller
• Process payments without confirming the total amount first


## 13. CALL ENDING SCRIPTS

**After Taking an Order:**
> "Perfect! I have your order for [items]. Your subtotal is [subtotal], plus [tax amount] tax [and delivery fee if applicable], for a total of [total]. I've processed your payment ending in [last 4 digits]. Your order will be ready for [pickup/delivery] at [time]. You should receive a confirmation [text/email] shortly. Is there anything else I can help you with?"


**After Scheduling an Appointment:**
> "Perfect! I have you scheduled for [service] on [date] at [time]. You'll receive a confirmation shortly. Is there anything else I can help you with today?"

**After Providing Information:**
> "I'm glad I could help! Is there anything else you'd like to know about {business_name}?"

**Before Transferring:**
> "I'm connecting you now. Please hold for just a moment."

**General Closing:**
> "Thank you for calling {business_name}! We look forward to serving you. Have a great day!"


## AVAILABLE TOOLS

You have access to the following capabilities:
• Calendar checking and appointment scheduling
• SMS/Email confirmation sending
• Basic information lookup

Use these tools naturally during conversations when appropriate.


## FINAL REMINDER

Your mission is to represent **{business_name}** professionally, handle calls efficiently, and create positive experiences that make customers want to return.

**Be helpful. Be honest. Be friendly.**
"""
    
    return {
        "success": True,
        "prompt": prompt,
        "business_name": business_name,
        "business_type": business_type,
        "sections": [
            "1. ROLE",
            "2. GREETING",
            "3. TONE",
            "4. SERVICES",
            "5. GOALS",
            "6. REQUIRED INFO",
            "7. BUSINESS INFO",
            "8. FAQ RULES",
            "9. ESCALATION",
            "10. AFTER HOURS",
            "11. CONSTRAINTS",
            "12. ENDING SCRIPT"
        ]
    }


# ========== Legacy Prompt Generate Endpoint (for compatibility) ==========

@router.post("/prompt/generate")
def generate_prompt_legacy(payload: GeneratePromptRequest, user=Depends(verify_token)):
    """
    Legacy endpoint - redirects to new generate-prompt
    """
    return generate_ai_prompt(payload, user)


# ========== Slack Integration ==========

from slack_integration import (
    notify_new_call,
    notify_call_ended,
    notify_appointment_scheduled,
    notify_order_placed,
    notify_escalation,
    notify_low_credits
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
    
    from db import get_conn, sql
    conn = get_conn()
    cur = conn.cursor()
    
    # Add columns if they don't exist (migration)
    from db import add_column_if_missing
    add_column_if_missing(conn, 'users', 'slack_bot_token', 'TEXT')
    add_column_if_missing(conn, 'users', 'slack_default_channel', 'TEXT')
    add_column_if_missing(conn, 'users', 'slack_enabled', 'BOOLEAN DEFAULT FALSE')
    
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
    Check if Slack is configured for this user
    """
    user_id = user["id"]
    
    from db import get_conn, sql
    conn = get_conn()
    cur = conn.cursor()
    
    try:
        cur.execute(sql("""
            SELECT slack_enabled, slack_default_channel
            FROM users
            WHERE id = {PH}
        """), (user_id,))
        
        row = cur.fetchone()
    except:
        # Columns don't exist yet
        conn.close()
        return {"configured": False}
    
    conn.close()
    
    if not row:
        return {"configured": False}
    
    if isinstance(row, dict):
        enabled = row.get('slack_enabled')
        channel = row.get('slack_default_channel')
    else:
        enabled = row[0] if row else False
        channel = row[1] if len(row) > 1 else None
    
    return {
        "configured": bool(enabled),
        "channel": channel or "#calls"
    }


@router.post("/slack/test")
def test_slack_notification(user=Depends(verify_token)):
    """
    Send a test notification to Slack
    """
    user_id = user["id"]
    
    # Get user's Slack token
    from db import get_conn, sql
    conn = get_conn()
    cur = conn.cursor()
    
    try:
        cur.execute(sql("""
            SELECT slack_bot_token, slack_default_channel
            FROM users
            WHERE id = {PH}
        """), (user_id,))
        
        row = cur.fetchone()
        conn.close()
        
        if not row:
            return {"success": False, "error": "Slack not configured"}
        
        if isinstance(row, dict):
            token = row.get('slack_bot_token')
            channel = row.get('slack_default_channel') or "#calls"
        else:
            token = row[0]
            channel = row[1] if len(row) > 1 else "#calls"
        
        if not token:
            return {"success": False, "error": "Slack token not found"}
        
        # Send test notification
        result = notify_new_call(
            agent_name="Test Agent",
            caller_number="+1-555-TEST",
            channel=channel,
            token=token
        )
        
        return result
        
    except Exception as e:
        conn.close()
        return {"success": False, "error": str(e)}


@router.post("/slack/disable")
def disable_slack(user=Depends(verify_token)):
    """
    Disable Slack notifications
    """
    user_id = user["id"]
    
    from db import get_conn, sql
    conn = get_conn()
    cur = conn.cursor()
    
    try:
        cur.execute(sql("""
            UPDATE users
            SET slack_enabled = FALSE
            WHERE id = {PH}
        """), (user_id,))
        
        conn.commit()
        conn.close()
        
        return {"success": True, "message": "Slack notifications disabled"}
    except Exception as e:
        conn.close()
        return {"success": False, "error": str(e)}
