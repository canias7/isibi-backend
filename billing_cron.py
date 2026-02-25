"""
Monthly Phone Number Billing System
Charges customers $1.15/month per phone number (Twilio's exact cost, no markup)
"""

import os
import sys
from datetime import datetime

# Add parent directory to path to import db module
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from db import get_conn, sql, deduct_credits

def charge_monthly_phone_fees():
    """
    Run this function monthly (via cron job) to charge customers for phone numbers.
    Deducts $1.15/month from each customer with active phone numbers.
    This is Twilio's exact cost - no markup.
    """
    conn = get_conn()
    cur = conn.cursor()
    
    # Get all agents with phone numbers (not deleted)
    cur.execute(sql("""
        SELECT 
            a.id as agent_id,
            a.name as agent_name,
            a.phone_number,
            a.owner_user_id,
            u.email
        FROM agents a
        JOIN users u ON a.owner_user_id = u.id
        WHERE a.phone_number IS NOT NULL 
        AND a.deleted_at IS NULL
        AND a.twilio_number_sid IS NOT NULL
    """))
    
    agents_with_numbers = cur.fetchall()
    conn.close()
    
    total_charged = 0
    total_agents = 0
    failed_charges = []
    
    print(f"\n{'='*60}")
    print(f"Starting Monthly Phone Number Billing")
    print(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Agents with phone numbers: {len(agents_with_numbers)}")
    print(f"{'='*60}\n")
    
    for row in agents_with_numbers:
        if isinstance(row, dict):
            agent_id = row['agent_id']
            agent_name = row['agent_name']
            phone_number = row['phone_number']
            user_id = row['owner_user_id']
            email = row['email']
        else:
            agent_id, agent_name, phone_number, user_id, email = row
        
        # Deduct $1.15 from customer's credits (Twilio's exact cost)
        result = deduct_credits(
            user_id=user_id,
            amount=1.15,  # Pass through Twilio's cost, no markup
            description=f"Monthly phone number fee: {phone_number} ({agent_name})"
        )
        
        if result["success"]:
            total_charged += 1.15
            total_agents += 1
            print(f"✅ Charged user_id={user_id} ({email}) $1.15 for {phone_number}")
        else:
            failed_charges.append({
                "user_id": user_id,
                "email": email,
                "agent_name": agent_name,
                "phone_number": phone_number,
                "error": result.get("error")
            })
            print(f"❌ Failed to charge user_id={user_id} ({email}): {result.get('error')}")
    
    # Summary report
    print(f"\n{'='*60}")
    print(f"Monthly Phone Number Billing Complete")
    print(f"{'='*60}")
    print(f"Total agents charged: {total_agents}")
    print(f"Total charged: ${total_charged:.2f}")
    print(f"Failed charges: {len(failed_charges)}")
    print(f"Success rate: {(total_agents / len(agents_with_numbers) * 100) if agents_with_numbers else 0:.1f}%")
    
    if failed_charges:
        print(f"\n⚠️  Failed Charges:")
        for failure in failed_charges:
            print(f"  - {failure['email']} ({failure['phone_number']})")
            print(f"    Agent: {failure['agent_name']}")
            print(f"    Error: {failure['error']}\n")
    
    print(f"{'='*60}\n")
    
    return {
        "total_charged": total_charged,
        "total_agents": total_agents,
        "failed_charges": failed_charges
    }


if __name__ == "__main__":
    # Run the billing
    result = charge_monthly_phone_fees()
    
    # Exit with error code if there were failures
    if result["failed_charges"]:
        sys.exit(1)
    else:
        sys.exit(0)
