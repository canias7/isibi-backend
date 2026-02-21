from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from auth_routes import verify_token  # your JWT verify function
from db import create_agent, list_agents, get_agent, update_agent, delete_agent, get_user_usage, get_call_history, get_user_credits, add_credits, get_credit_transactions, get_user_google_credentials, assign_google_calendar_to_agent
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
        raise HTTPException(status_code=503, detail="Twilio not configured")
    
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
            "your_price": 5.00  # What customer pays
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")


@router.post("/phone/purchase")
def purchase_phone_number(payload: PurchaseNumberRequest, user=Depends(verify_token)):
    """
    Purchase a Twilio phone number (BEFORE creating agent)
    Returns the number so it can be used when creating the agent
    """
    if not twilio_client:
        raise HTTPException(status_code=503, detail="Twilio not configured")
    
    user_id = user["id"]
    
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
        
        # Purchase the number
        purchased_number = twilio_client.incoming_phone_numbers.create(
            phone_number=available_numbers[0].phone_number,
            voice_url=f"{BACKEND_URL}/incoming-call",
            voice_method="POST",
            friendly_name=f"User {user_id} - Reserved"  # Mark as reserved until agent is created
        )
        
        return {
            "success": True,
            "phone_number": purchased_number.phone_number,
            "twilio_sid": purchased_number.sid,
            "friendly_name": purchased_number.friendly_name,
            "monthly_cost": 5.00,  # What you charge customer
            "message": f"Phone number {purchased_number.phone_number} is ready! Use it when creating your agent."
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Purchase failed: {str(e)}")


@router.post("/phone/release/{twilio_sid}")
def release_phone_number_by_sid(twilio_sid: str, user=Depends(verify_token)):
    """
    Release a Twilio number that was purchased but not used
    (In case user changes their mind before creating agent)
    """
    if not twilio_client:
        raise HTTPException(status_code=503, detail="Twilio not configured")
    
    try:
        # Release the Twilio number
        twilio_client.incoming_phone_numbers(twilio_sid).delete()
        
        return {
            "success": True,
            "message": "Phone number released successfully"
        }
        
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
                "monthly_cost": 5.00
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
        "monthly_cost": 5.00 if agent.get("phone_number") else 0.00
    }
