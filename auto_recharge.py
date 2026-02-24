import os
import stripe
from datetime import datetime

# Initialize Stripe
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY")
stripe.api_key = STRIPE_SECRET_KEY

# Auto-recharge settings
AUTO_RECHARGE_THRESHOLD = 2.00  # Trigger when balance < $2
AUTO_RECHARGE_AMOUNT = 10.00    # Add $10 when triggered


def check_and_auto_recharge(user_id: int, current_balance: float) -> dict:
    """
    Check if user's balance is low and auto-recharge if enabled
    
    Args:
        user_id: User ID
        current_balance: Current credit balance
    
    Returns:
        {
            "triggered": bool,
            "success": bool,
            "amount_added": float,
            "new_balance": float,
            "payment_id": str,
            "error": str (if failed)
        }
    """
    from db import get_conn, sql
    
    # Check if balance is below threshold
    if current_balance >= AUTO_RECHARGE_THRESHOLD:
        return {
            "triggered": False,
            "message": "Balance above threshold"
        }
    
    # Get user's auto-recharge settings
    conn = get_conn()
    cur = conn.cursor()
    
    try:
        cur.execute(sql("""
            SELECT auto_recharge_enabled, auto_recharge_amount, stripe_customer_id, stripe_payment_method_id
            FROM users
            WHERE id = {PH}
        """), (user_id,))
        
        row = cur.fetchone()
        
        if not row:
            conn.close()
            return {"triggered": False, "error": "User not found"}
        
        # Parse row
        if isinstance(row, dict):
            auto_enabled = row.get('auto_recharge_enabled')
            recharge_amount = row.get('auto_recharge_amount') or AUTO_RECHARGE_AMOUNT
            customer_id = row.get('stripe_customer_id')
            payment_method_id = row.get('stripe_payment_method_id')
        else:
            auto_enabled = row[0] if len(row) > 0 else False
            recharge_amount = row[1] if len(row) > 1 else AUTO_RECHARGE_AMOUNT
            customer_id = row[2] if len(row) > 2 else None
            payment_method_id = row[3] if len(row) > 3 else None
        
        # Check if auto-recharge is enabled
        if not auto_enabled:
            conn.close()
            return {"triggered": False, "message": "Auto-recharge not enabled"}
        
        # Check if payment method is saved
        if not customer_id or not payment_method_id:
            conn.close()
            return {
                "triggered": True,
                "success": False,
                "error": "No payment method on file"
            }
        
        # Process auto-recharge payment
        try:
            # Create payment intent
            payment_intent = stripe.PaymentIntent.create(
                amount=int(recharge_amount * 100),  # Convert to cents
                currency="usd",
                customer=customer_id,
                payment_method=payment_method_id,
                off_session=True,  # Customer not present
                confirm=True,  # Confirm immediately
                description=f"Auto-recharge: ${recharge_amount:.2f} credits"
            )
            
            if payment_intent.status == "succeeded":
                # Add credits to user's balance
                from db import add_credits
                result = add_credits(
                    user_id=user_id,
                    amount=recharge_amount,
                    description=f"Auto-recharge (balance was ${current_balance:.2f})"
                )
                
                if result["success"]:
                    conn.close()
                    
                    # Log the auto-recharge
                    print(f"✅ Auto-recharge successful: User {user_id} - ${recharge_amount}")
                    
                    return {
                        "triggered": True,
                        "success": True,
                        "amount_added": recharge_amount,
                        "old_balance": current_balance,
                        "new_balance": result["balance"],
                        "payment_id": payment_intent.id,
                        "message": f"Auto-recharged ${recharge_amount:.2f}"
                    }
                else:
                    conn.close()
                    return {
                        "triggered": True,
                        "success": False,
                        "error": "Payment succeeded but failed to add credits"
                    }
            else:
                conn.close()
                return {
                    "triggered": True,
                    "success": False,
                    "error": f"Payment failed: {payment_intent.status}"
                }
        
        except stripe.error.CardError as e:
            conn.close()
            return {
                "triggered": True,
                "success": False,
                "error": f"Card declined: {e.user_message}"
            }
        
        except Exception as e:
            conn.close()
            return {
                "triggered": True,
                "success": False,
                "error": str(e)
            }
    
    except Exception as e:
        conn.close()
        return {
            "triggered": True,
            "success": False,
            "error": f"Database error: {str(e)}"
        }


def save_payment_method_for_auto_recharge(user_id: int, payment_method_id: str) -> dict:
    """
    Save a payment method for auto-recharge
    
    Args:
        user_id: User ID
        payment_method_id: Stripe payment method ID
    
    Returns:
        {"success": bool, "error": str (if failed)}
    """
    from db import get_conn, sql
    
    try:
        # Get or create Stripe customer
        conn = get_conn()
        cur = conn.cursor()
        
        cur.execute(sql("""
            SELECT stripe_customer_id, email
            FROM users
            WHERE id = {PH}
        """), (user_id,))
        
        row = cur.fetchone()
        
        if not row:
            conn.close()
            return {"success": False, "error": "User not found"}
        
        if isinstance(row, dict):
            customer_id = row.get('stripe_customer_id')
            email = row.get('email')
        else:
            customer_id = row[0]
            email = row[1]
        
        # Create Stripe customer if doesn't exist
        if not customer_id:
            customer = stripe.Customer.create(
                email=email,
                payment_method=payment_method_id,
                invoice_settings={
                    "default_payment_method": payment_method_id
                }
            )
            customer_id = customer.id
        else:
            # Attach payment method to existing customer
            stripe.PaymentMethod.attach(
                payment_method_id,
                customer=customer_id
            )
            
            # Set as default
            stripe.Customer.modify(
                customer_id,
                invoice_settings={
                    "default_payment_method": payment_method_id
                }
            )
        
        # Save to database
        cur.execute(sql("""
            UPDATE users
            SET stripe_customer_id = {PH},
                stripe_payment_method_id = {PH}
            WHERE id = {PH}
        """), (customer_id, payment_method_id, user_id))
        
        conn.commit()
        conn.close()
        
        return {
            "success": True,
            "customer_id": customer_id,
            "payment_method_id": payment_method_id
        }
    
    except Exception as e:
        return {"success": False, "error": str(e)}
