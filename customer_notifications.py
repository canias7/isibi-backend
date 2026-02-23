import os
from datetime import datetime

# Twilio will use the same client as calls
try:
    from twilio.rest import Client
    TWILIO_AVAILABLE = True
except ImportError:
    TWILIO_AVAILABLE = False
    print("⚠️ Twilio not available")

# Initialize Twilio
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_PHONE_NUMBER = os.getenv("TWILIO_PHONE_NUMBER")  # Your business number for SMS

twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN) if (TWILIO_AVAILABLE and TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN) else None


def send_order_confirmation_sms(
    customer_phone: str,
    business_name: str,
    order_items: str,
    total: float,
    pickup_time: str = None,
    delivery_address: str = None,
    order_number: str = None,
    from_number: str = None
):
    """
    Send order confirmation SMS to customer
    
    Args:
        customer_phone: Customer's phone number (e.g., "+17045551234")
        business_name: Name of the business
        order_items: Description of items ordered
        total: Total amount charged
        pickup_time: When to pickup (optional)
        delivery_address: Delivery address (optional)
        order_number: Order confirmation number (optional)
        from_number: Phone number to send from (defaults to TWILIO_PHONE_NUMBER)
    """
    if not twilio_client:
        print("⚠️ Twilio not configured - SMS skipped")
        return {"success": False, "error": "Twilio not configured"}
    
    # Use provided number or default
    send_from = from_number or TWILIO_PHONE_NUMBER
    
    if not send_from:
        return {"success": False, "error": "No sending number configured"}
    
    # Build message
    message_parts = [
        f"Thank you for your order from {business_name}!",
        "",
        f"📦 {order_items}",
        f"💰 Total: ${total:.2f}"
    ]
    
    if pickup_time:
        message_parts.append(f"⏰ Ready for pickup: {pickup_time}")
    
    if delivery_address:
        message_parts.append(f"📍 Delivering to: {delivery_address}")
    
    if order_number:
        message_parts.append(f"Order #{order_number}")
    
    message_parts.append("")
    message_parts.append("Questions? Just call us back!")
    
    message = "\n".join(message_parts)
    
    try:
        sms = twilio_client.messages.create(
            body=message,
            from_=send_from,
            to=customer_phone
        )
        
        print(f"✅ Order confirmation SMS sent to {customer_phone}")
        
        return {
            "success": True,
            "message_sid": sms.sid,
            "to": customer_phone,
            "message": "Order confirmation sent via SMS"
        }
    except Exception as e:
        print(f"❌ SMS send failed: {str(e)}")
        return {"success": False, "error": str(e)}


def send_appointment_confirmation_sms(
    customer_phone: str,
    business_name: str,
    customer_name: str,
    service: str,
    date: str,
    time: str,
    confirmation_number: str = None,
    from_number: str = None
):
    """
    Send appointment confirmation SMS to customer
    """
    if not twilio_client:
        print("⚠️ Twilio not configured - SMS skipped")
        return {"success": False, "error": "Twilio not configured"}
    
    send_from = from_number or TWILIO_PHONE_NUMBER
    
    if not send_from:
        return {"success": False, "error": "No sending number configured"}
    
    message_parts = [
        f"Appointment Confirmed at {business_name}!",
        "",
        f"👤 {customer_name}",
        f"✂️ {service}",
        f"📅 {date}",
        f"⏰ {time}"
    ]
    
    if confirmation_number:
        message_parts.append(f"Confirmation: {confirmation_number}")
    
    message_parts.append("")
    message_parts.append("Need to reschedule? Call us!")
    
    message = "\n".join(message_parts)
    
    try:
        sms = twilio_client.messages.create(
            body=message,
            from_=send_from,
            to=customer_phone
        )
        
        print(f"✅ Appointment confirmation SMS sent to {customer_phone}")
        
        return {
            "success": True,
            "message_sid": sms.sid,
            "to": customer_phone,
            "message": "Appointment confirmation sent via SMS"
        }
    except Exception as e:
        print(f"❌ SMS send failed: {str(e)}")
        return {"success": False, "error": str(e)}


def send_payment_receipt_sms(
    customer_phone: str,
    business_name: str,
    amount: float,
    card_last_4: str,
    description: str = "Payment",
    from_number: str = None
):
    """
    Send payment receipt SMS to customer
    """
    if not twilio_client:
        print("⚠️ Twilio not configured - SMS skipped")
        return {"success": False, "error": "Twilio not configured"}
    
    send_from = from_number or TWILIO_PHONE_NUMBER
    
    if not send_from:
        return {"success": False, "error": "No sending number configured"}
    
    message = f"""Payment Receipt - {business_name}

💳 {description}
Amount: ${amount:.2f}
Card ending in: {card_last_4}

Thank you for your business!"""
    
    try:
        sms = twilio_client.messages.create(
            body=message,
            from_=send_from,
            to=customer_phone
        )
        
        print(f"✅ Payment receipt SMS sent to {customer_phone}")
        
        return {
            "success": True,
            "message_sid": sms.sid,
            "to": customer_phone,
            "message": "Payment receipt sent via SMS"
        }
    except Exception as e:
        print(f"❌ SMS send failed: {str(e)}")
        return {"success": False, "error": str(e)}
