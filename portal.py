

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
    """
    Get admin dashboard statistics
    
    Requires admin privileges
    """
    stats = get_admin_dashboard_stats()
    return stats


@router.get("/admin/users")
def get_admin_users(user=Depends(verify_admin), limit: int = 100, offset: int = 0):
    """
    Get all users with statistics
    
    Requires admin privileges
    """
    users = get_all_users(limit=limit, offset=offset)
    return {"users": users, "total": len(users)}


@router.get("/admin/activity")
def get_admin_activity(user=Depends(verify_admin), limit: int = 50):
    """
    Get recent platform activity
    
    Requires admin privileges
    """
    activity = get_recent_activity(limit=limit)
    return {"activity": activity}


@router.get("/admin/revenue-chart")
def get_admin_revenue_chart(user=Depends(verify_admin), days: int = 30):
    """
    Get revenue chart data
    
    Requires admin privileges
    """
    chart_data = get_revenue_chart_data(days=days)
    return chart_data


@router.get("/admin/voice-chat-logs")
def get_admin_voice_chat_logs(user=Depends(verify_admin), limit: int = 50):
    """
    Get voice chat logs from "Talk to ISIBI"
    
    Requires admin privileges
    """
    from db import get_conn, sql
    
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
    """
    Manually add credits to a user (admin only)
    """
    from db import add_credits
    
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
