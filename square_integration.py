import os
import uuid
from datetime import datetime

# Square SDK
try:
    from square.client import Client
    SQUARE_AVAILABLE = True
except ImportError:
    SQUARE_AVAILABLE = False
    print("⚠️ Square SDK not installed. Run: pip install squareup")

# Initialize Square client
SQUARE_ACCESS_TOKEN = os.getenv("SQUARE_ACCESS_TOKEN")
SQUARE_ENVIRONMENT = os.getenv("SQUARE_ENVIRONMENT", "sandbox")  # 'sandbox' or 'production'

square_client = None
if SQUARE_AVAILABLE and SQUARE_ACCESS_TOKEN:
    square_client = Client(
        access_token=SQUARE_ACCESS_TOKEN,
        environment=SQUARE_ENVIRONMENT
    )


def create_payment(
    amount_cents: int,
    card_number: str,
    exp_month: str,
    exp_year: str,
    cvv: str,
    postal_code: str,
    customer_name: str = None,
    description: str = None,
    reference_id: str = None
):
    """
    Process a payment through Square
    
    Args:
        amount_cents: Amount in cents (e.g., 2999 for $29.99)
        card_number: Credit card number
        exp_month: Expiration month (MM)
        exp_year: Expiration year (YYYY)
        cvv: CVV code
        postal_code: Billing ZIP code
        customer_name: Customer name (optional)
        description: Payment description (optional)
        reference_id: Your internal reference ID (optional)
    
    Returns:
        {
            "success": bool,
            "payment_id": str,
            "amount": float,
            "card_last_4": str,
            "error": str (if failed)
        }
    """
    if not square_client:
        return {"success": False, "error": "Square not configured"}
    
    try:
        # Generate idempotency key (prevents duplicate charges)
        idempotency_key = str(uuid.uuid4())
        
        # Create source (tokenize card)
        # In production, you'd use Square's Web Payments SDK to tokenize on frontend
        # For phone orders, we create the card nonce directly
        card_nonce_result = square_client.cards.create_card(
            body={
                "idempotency_key": str(uuid.uuid4()),
                "source_id": "EXTERNAL",  # External payment source
                "card": {
                    "number": card_number.replace(" ", "").replace("-", ""),
                    "exp_month": int(exp_month),
                    "exp_year": int(exp_year),
                    "cvv": cvv,
                    "billing_address": {
                        "postal_code": postal_code
                    },
                    "cardholder_name": customer_name
                }
            }
        )
        
        if not card_nonce_result.is_success():
            error = card_nonce_result.errors[0] if card_nonce_result.errors else "Unknown error"
            return {"success": False, "error": f"Card tokenization failed: {error}"}
        
        card_id = card_nonce_result.body['card']['id']
        
        # Create payment
        payment_result = square_client.payments.create_payment(
            body={
                "idempotency_key": idempotency_key,
                "source_id": card_id,
                "amount_money": {
                    "amount": amount_cents,
                    "currency": "USD"
                },
                "note": description,
                "reference_id": reference_id
            }
        )
        
        if payment_result.is_success():
            payment = payment_result.body['payment']
            
            # Get card details
            card_details = payment.get('card_details', {})
            card_last_4 = card_details.get('card', {}).get('last_4', 'XXXX')
            
            return {
                "success": True,
                "payment_id": payment['id'],
                "amount": amount_cents / 100.0,
                "card_last_4": card_last_4,
                "status": payment['status'],
                "created_at": payment['created_at']
            }
        else:
            errors = payment_result.errors
            error_msg = errors[0]['detail'] if errors else "Payment failed"
            return {"success": False, "error": error_msg}
    
    except Exception as e:
        return {"success": False, "error": str(e)}


def create_customer(email: str, given_name: str, family_name: str = None, phone_number: str = None):
    """
    Create a customer in Square
    
    Args:
        email: Customer email
        given_name: First name
        family_name: Last name (optional)
        phone_number: Phone number (optional)
    
    Returns:
        {
            "success": bool,
            "customer_id": str,
            "error": str (if failed)
        }
    """
    if not square_client:
        return {"success": False, "error": "Square not configured"}
    
    try:
        result = square_client.customers.create_customer(
            body={
                "idempotency_key": str(uuid.uuid4()),
                "email_address": email,
                "given_name": given_name,
                "family_name": family_name,
                "phone_number": phone_number
            }
        )
        
        if result.is_success():
            customer = result.body['customer']
            return {
                "success": True,
                "customer_id": customer['id']
            }
        else:
            errors = result.errors
            error_msg = errors[0]['detail'] if errors else "Failed to create customer"
            return {"success": False, "error": error_msg}
    
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_payment(payment_id: str):
    """
    Retrieve payment details
    
    Args:
        payment_id: Square payment ID
    
    Returns:
        Payment details dict or error
    """
    if not square_client:
        return {"success": False, "error": "Square not configured"}
    
    try:
        result = square_client.payments.get_payment(payment_id=payment_id)
        
        if result.is_success():
            return {
                "success": True,
                "payment": result.body['payment']
            }
        else:
            return {"success": False, "error": "Payment not found"}
    
    except Exception as e:
        return {"success": False, "error": str(e)}


def refund_payment(payment_id: str, amount_cents: int = None, reason: str = None):
    """
    Refund a payment (partial or full)
    
    Args:
        payment_id: Square payment ID
        amount_cents: Amount to refund in cents (None for full refund)
        reason: Reason for refund (optional)
    
    Returns:
        {
            "success": bool,
            "refund_id": str,
            "error": str (if failed)
        }
    """
    if not square_client:
        return {"success": False, "error": "Square not configured"}
    
    try:
        body = {
            "idempotency_key": str(uuid.uuid4()),
            "payment_id": payment_id,
            "reason": reason
        }
        
        # Add amount if partial refund
        if amount_cents:
            body["amount_money"] = {
                "amount": amount_cents,
                "currency": "USD"
            }
        
        result = square_client.refunds.refund_payment(body=body)
        
        if result.is_success():
            refund = result.body['refund']
            return {
                "success": True,
                "refund_id": refund['id'],
                "amount": refund['amount_money']['amount'] / 100.0,
                "status": refund['status']
            }
        else:
            errors = result.errors
            error_msg = errors[0]['detail'] if errors else "Refund failed"
            return {"success": False, "error": error_msg}
    
    except Exception as e:
        return {"success": False, "error": str(e)}


def list_payments(begin_time: str = None, end_time: str = None, limit: int = 100):
    """
    List payments within a time range
    
    Args:
        begin_time: ISO 8601 timestamp (e.g., "2024-01-01T00:00:00Z")
        end_time: ISO 8601 timestamp
        limit: Max results (default 100)
    
    Returns:
        List of payments
    """
    if not square_client:
        return {"success": False, "error": "Square not configured"}
    
    try:
        body = {}
        if begin_time:
            body["begin_time"] = begin_time
        if end_time:
            body["end_time"] = end_time
        body["limit"] = limit
        
        result = square_client.payments.list_payments(**body)
        
        if result.is_success():
            return {
                "success": True,
                "payments": result.body.get('payments', [])
            }
        else:
            return {"success": False, "error": "Failed to list payments"}
    
    except Exception as e:
        return {"success": False, "error": str(e)}
