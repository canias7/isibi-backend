import os
from datetime import datetime, timedelta
from typing import Dict, List

def get_admin_dashboard_stats() -> Dict:
    """
    Get comprehensive dashboard statistics for admin
    
    Returns:
        {
            "users": {...},
            "revenue": {...},
            "calls": {...},
            "agents": {...},
            "credits": {...}
        }
    """
    from db import get_conn, sql
    
    try:
        conn = get_conn()
        cur = conn.cursor()
        
        # Get date ranges
        today = datetime.now().date()
        week_ago = today - timedelta(days=7)
        month_ago = today - timedelta(days=30)
        
        # === USER STATISTICS ===
        cur.execute("""
            SELECT 
                COUNT(*) as total_users,
                COUNT(CASE WHEN created_at >= CURRENT_DATE - INTERVAL '7 days' THEN 1 END) as new_users_week,
                COUNT(CASE WHEN created_at >= CURRENT_DATE - INTERVAL '30 days' THEN 1 END) as new_users_month
            FROM users
        """)
        user_stats = cur.fetchone()
        
        # === REVENUE STATISTICS ===
        cur.execute("""
            SELECT 
                COALESCE(SUM(amount), 0) as total_revenue,
                COALESCE(SUM(CASE WHEN created_at >= CURRENT_DATE - INTERVAL '7 days' THEN amount END), 0) as revenue_week,
                COALESCE(SUM(CASE WHEN created_at >= CURRENT_DATE - INTERVAL '30 days' THEN amount END), 0) as revenue_month
            FROM credit_transactions
            WHERE type = 'purchase'
        """)
        revenue_stats = cur.fetchone()
        
        # === CALL STATISTICS ===
        cur.execute("""
            SELECT 
                COUNT(*) as total_calls,
                COUNT(CASE WHEN created_at >= CURRENT_DATE - INTERVAL '7 days' THEN 1 END) as calls_week,
                COUNT(CASE WHEN created_at >= CURRENT_DATE - INTERVAL '30 days' THEN 1 END) as calls_month,
                COALESCE(AVG(EXTRACT(EPOCH FROM (ended_at - started_at))), 0) as avg_duration_seconds
            FROM calls
            WHERE ended_at IS NOT NULL
        """)
        call_stats = cur.fetchone()
        
        # === AGENT STATISTICS ===
        cur.execute("""
            SELECT 
                COUNT(*) as total_agents,
                COUNT(CASE WHEN created_at >= CURRENT_DATE - INTERVAL '7 days' THEN 1 END) as new_agents_week,
                COUNT(DISTINCT owner_user_id) as active_users_with_agents
            FROM agents
        """)
        agent_stats = cur.fetchone()
        
        # === CREDIT STATISTICS ===
        cur.execute("""
            SELECT 
                COALESCE(SUM(balance), 0) as total_balance,
                COALESCE(SUM(total_purchased), 0) as total_purchased,
                COALESCE(SUM(total_used), 0) as total_used
            FROM user_credits
        """)
        credit_stats = cur.fetchone()
        
        conn.close()
        
        # Format results
        return {
            "users": {
                "total": user_stats[0] if user_stats else 0,
                "new_week": user_stats[1] if user_stats else 0,
                "new_month": user_stats[2] if user_stats else 0
            },
            "revenue": {
                "total": float(revenue_stats[0]) if revenue_stats else 0.0,
                "week": float(revenue_stats[1]) if revenue_stats else 0.0,
                "month": float(revenue_stats[2]) if revenue_stats else 0.0
            },
            "calls": {
                "total": call_stats[0] if call_stats else 0,
                "week": call_stats[1] if call_stats else 0,
                "month": call_stats[2] if call_stats else 0,
                "avg_duration": int(call_stats[3]) if call_stats else 0
            },
            "agents": {
                "total": agent_stats[0] if agent_stats else 0,
                "new_week": agent_stats[1] if agent_stats else 0,
                "active_users": agent_stats[2] if agent_stats else 0
            },
            "credits": {
                "total_balance": float(credit_stats[0]) if credit_stats else 0.0,
                "total_purchased": float(credit_stats[1]) if credit_stats else 0.0,
                "total_used": float(credit_stats[2]) if credit_stats else 0.0
            }
        }
    
    except Exception as e:
        print(f"❌ Failed to get admin stats: {e}")
        return {
            "users": {"total": 0, "new_week": 0, "new_month": 0},
            "revenue": {"total": 0, "week": 0, "month": 0},
            "calls": {"total": 0, "week": 0, "month": 0, "avg_duration": 0},
            "agents": {"total": 0, "new_week": 0, "active_users": 0},
            "credits": {"total_balance": 0, "total_purchased": 0, "total_used": 0}
        }


def get_all_users(limit: int = 100, offset: int = 0) -> List[Dict]:
    """
    Get all users with their statistics
    
    Returns:
        List of users with credits, agents, calls
    """
    from db import get_conn, sql
    
    try:
        conn = get_conn()
        cur = conn.cursor()
        
        cur.execute(sql("""
            SELECT 
                u.id,
                u.email,
                u.created_at,
                COALESCE(uc.balance, 0) as balance,
                COALESCE(uc.total_purchased, 0) as total_purchased,
                COALESCE(uc.total_used, 0) as total_used,
                COUNT(DISTINCT a.id) as agent_count,
                COUNT(DISTINCT c.id) as call_count
            FROM users u
            LEFT JOIN user_credits uc ON u.id = uc.user_id
            LEFT JOIN agents a ON u.id = a.owner_user_id
            LEFT JOIN calls c ON u.id = c.user_id
            GROUP BY u.id, u.email, u.created_at, uc.balance, uc.total_purchased, uc.total_used
            ORDER BY u.created_at DESC
            LIMIT {PH} OFFSET {PH}
        """), (limit, offset))
        
        users = []
        for row in cur.fetchall():
            if isinstance(row, dict):
                users.append({
                    "id": row['id'],
                    "email": row['email'],
                    "created_at": row['created_at'].isoformat() if row['created_at'] else None,
                    "balance": float(row['balance']),
                    "total_purchased": float(row['total_purchased']),
                    "total_used": float(row['total_used']),
                    "agent_count": row['agent_count'],
                    "call_count": row['call_count']
                })
            else:
                users.append({
                    "id": row[0],
                    "email": row[1],
                    "created_at": row[2].isoformat() if row[2] else None,
                    "balance": float(row[3]),
                    "total_purchased": float(row[4]),
                    "total_used": float(row[5]),
                    "agent_count": row[6],
                    "call_count": row[7]
                })
        
        conn.close()
        return users
    
    except Exception as e:
        print(f"❌ Failed to get users: {e}")
        return []


def get_recent_activity(limit: int = 50) -> List[Dict]:
    """
    Get recent platform activity (calls, purchases, signups)
    
    Returns:
        List of recent activities
    """
    from db import get_conn, sql
    
    try:
        conn = get_conn()
        cur = conn.cursor()
        
        activities = []
        
        # Recent calls
        cur.execute(sql("""
            SELECT 
                'call' as type,
                c.id,
                c.created_at,
                u.email as user_email,
                a.name as agent_name,
                EXTRACT(EPOCH FROM (c.ended_at - c.started_at)) as duration
            FROM calls c
            JOIN users u ON c.user_id = u.id
            LEFT JOIN agents a ON c.agent_id = a.id
            WHERE c.created_at >= CURRENT_DATE - INTERVAL '7 days'
            ORDER BY c.created_at DESC
            LIMIT {PH}
        """), (limit,))
        
        for row in cur.fetchall():
            if isinstance(row, dict):
                activities.append({
                    "type": "call",
                    "id": row['id'],
                    "timestamp": row['created_at'].isoformat() if row['created_at'] else None,
                    "user_email": row['user_email'],
                    "details": f"Call to {row['agent_name']} ({int(row['duration'] or 0)}s)"
                })
            else:
                activities.append({
                    "type": "call",
                    "id": row[1],
                    "timestamp": row[2].isoformat() if row[2] else None,
                    "user_email": row[3],
                    "details": f"Call to {row[4]} ({int(row[5] or 0)}s)"
                })
        
        # Recent credit purchases
        cur.execute(sql("""
            SELECT 
                'purchase' as type,
                ct.id,
                ct.created_at,
                u.email as user_email,
                ct.amount
            FROM credit_transactions ct
            JOIN users u ON ct.user_id = u.id
            WHERE ct.type = 'purchase'
            AND ct.created_at >= CURRENT_DATE - INTERVAL '7 days'
            ORDER BY ct.created_at DESC
            LIMIT {PH}
        """), (limit,))
        
        for row in cur.fetchall():
            if isinstance(row, dict):
                activities.append({
                    "type": "purchase",
                    "id": row['id'],
                    "timestamp": row['created_at'].isoformat() if row['created_at'] else None,
                    "user_email": row['user_email'],
                    "details": f"Purchased ${row['amount']:.2f} credits"
                })
            else:
                activities.append({
                    "type": "purchase",
                    "id": row[1],
                    "timestamp": row[2].isoformat() if row[2] else None,
                    "user_email": row[3],
                    "details": f"Purchased ${row[4]:.2f} credits"
                })
        
        # Recent signups
        cur.execute(sql("""
            SELECT 
                'signup' as type,
                id,
                created_at,
                email
            FROM users
            WHERE created_at >= CURRENT_DATE - INTERVAL '7 days'
            ORDER BY created_at DESC
            LIMIT {PH}
        """), (limit,))
        
        for row in cur.fetchall():
            if isinstance(row, dict):
                activities.append({
                    "type": "signup",
                    "id": row['id'],
                    "timestamp": row['created_at'].isoformat() if row['created_at'] else None,
                    "user_email": row['email'],
                    "details": "New user signup"
                })
            else:
                activities.append({
                    "type": "signup",
                    "id": row[1],
                    "timestamp": row[2].isoformat() if row[2] else None,
                    "user_email": row[3],
                    "details": "New user signup"
                })
        
        conn.close()
        
        # Sort all activities by timestamp
        activities.sort(key=lambda x: x['timestamp'], reverse=True)
        
        return activities[:limit]
    
    except Exception as e:
        print(f"❌ Failed to get recent activity: {e}")
        return []


def get_revenue_chart_data(days: int = 30) -> Dict:
    """
    Get revenue data for charts
    
    Returns:
        {"labels": [...], "data": [...]}
    """
    from db import get_conn, sql
    
    try:
        conn = get_conn()
        cur = conn.cursor()
        
        cur.execute(sql("""
            SELECT 
                DATE(created_at) as date,
                SUM(amount) as revenue
            FROM credit_transactions
            WHERE type = 'purchase'
            AND created_at >= CURRENT_DATE - INTERVAL '{} days'
            GROUP BY DATE(created_at)
            ORDER BY date ASC
        """).replace('{}', str(days)))
        
        labels = []
        data = []
        
        for row in cur.fetchall():
            if isinstance(row, dict):
                labels.append(row['date'].strftime('%Y-%m-%d'))
                data.append(float(row['revenue']))
            else:
                labels.append(row[0].strftime('%Y-%m-%d'))
                data.append(float(row[1]))
        
        conn.close()
        
        return {"labels": labels, "data": data}
    
    except Exception as e:
        print(f"❌ Failed to get revenue chart data: {e}")
        return {"labels": [], "data": []}


def is_admin(user_id: int) -> bool:
    """
    Check if user is an admin
    For now, you can set this manually or check email
    """
    from db import get_conn, sql
    
    try:
        conn = get_conn()
        cur = conn.cursor()
        
        # Get user email
        cur.execute(sql("SELECT email FROM users WHERE id = {PH}"), (user_id,))
        row = cur.fetchone()
        conn.close()
        
        if not row:
            return False
        
        email = row[0] if isinstance(row, tuple) else row.get('email')
        
        # Admin emails (you can add yours here)
        ADMIN_EMAILS = os.getenv("ADMIN_EMAILS", "").split(",")
        
        return email.lower().strip() in [e.lower().strip() for e in ADMIN_EMAILS if e]
    
    except Exception as e:
        print(f"❌ Failed to check admin: {e}")
        return False
