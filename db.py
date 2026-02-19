import sqlite3
import json
import os

DB_PATH = os.getenv("DB_PATH", "app.db")
def get_conn():
    conn = sqlite3.connect(DB_PATH, timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout=30000;")
    return conn

def add_column_if_missing(conn, table, column, coltype):
    cur = conn.cursor()
    cur.execute(f"PRAGMA table_info({table})")
    cols = [row[1] for row in cur.fetchall()]
    if column not in cols:
        cur.execute(f"ALTER TABLE {table} ADD COLUMN {column} {coltype}")
        conn.commit()

def init_db():
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS tenants (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        phone_number TEXT UNIQUE,
        agent_prompt TEXT
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        tenant_phone TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS agents (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        owner_user_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        business_name TEXT,
        system_prompt TEXT,
        voice TEXT,
        provider TEXT,
        phone_number TEXT,
        assistant_name TEXT,
        first_message TEXT,
        tools_json TEXT,
        google_calendar_credentials TEXT,
        google_calendar_id TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(owner_user_id) REFERENCES users(id)
    )
    """)
    
    # Usage tracking table
    cur.execute("""
    CREATE TABLE IF NOT EXISTS call_usage (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        agent_id INTEGER NOT NULL,
        call_sid TEXT,
        call_from TEXT,
        call_to TEXT,
        duration_seconds INTEGER DEFAULT 0,
        cost_usd REAL DEFAULT 0.0,
        revenue_usd REAL DEFAULT 0.0,
        profit_usd REAL DEFAULT 0.0,
        started_at TEXT DEFAULT CURRENT_TIMESTAMP,
        ended_at TEXT,
        status TEXT DEFAULT 'active',
        FOREIGN KEY(user_id) REFERENCES users(id),
        FOREIGN KEY(agent_id) REFERENCES agents(id)
    )
    """)
    
    # Monthly usage summary table
    cur.execute("""
    CREATE TABLE IF NOT EXISTS monthly_usage (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        month TEXT NOT NULL,
        total_calls INTEGER DEFAULT 0,
        total_minutes REAL DEFAULT 0.0,
        total_cost_usd REAL DEFAULT 0.0,
        total_revenue_usd REAL DEFAULT 0.0,
        total_profit_usd REAL DEFAULT 0.0,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(user_id) REFERENCES users(id),
        UNIQUE(user_id, month)
    )
    """)
    
    # Credits balance table
    cur.execute("""
    CREATE TABLE IF NOT EXISTS user_credits (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL UNIQUE,
        balance REAL DEFAULT 0.0,
        total_purchased REAL DEFAULT 0.0,
        total_used REAL DEFAULT 0.0,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(user_id) REFERENCES users(id)
    )
    """)
    
    # Credit transactions table (purchases and usage)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS credit_transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        amount REAL NOT NULL,
        type TEXT NOT NULL,
        description TEXT,
        balance_after REAL NOT NULL,
        call_id INTEGER,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(user_id) REFERENCES users(id),
        FOREIGN KEY(call_id) REFERENCES call_usage(id)
    )
    """)
    
    # Pricing plans table
    cur.execute("""
    CREATE TABLE IF NOT EXISTS pricing_plans (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        price_per_minute REAL NOT NULL,
        included_minutes INTEGER DEFAULT 0,
        monthly_fee REAL DEFAULT 0.0,
        active INTEGER DEFAULT 1
    )
    """)

    # --- MIGRATIONS (keep Render DB in sync) ---
    add_column_if_missing(conn, "agents", "phone_number", "TEXT")
    add_column_if_missing(conn, "agents", "provider", "TEXT")
    add_column_if_missing(conn, "agents", "first_message", "TEXT")
    add_column_if_missing(conn, "agents", "business_name", "TEXT")
    add_column_if_missing(conn, "agents", "assistant_name", "TEXT")
    add_column_if_missing(conn, "agents", "system_prompt", "TEXT")
    add_column_if_missing(conn, "agents", "voice", "TEXT")
    add_column_if_missing(conn, "agents", "tools_json", "TEXT")  # store JSON as TEXT
    add_column_if_missing(conn, "agents", "settings_json", "TEXT")  # for future use
    add_column_if_missing(conn, "agents", "google_calendar_credentials", "TEXT")  # Google OAuth tokens
    add_column_if_missing(conn, "agents", "google_calendar_id", "TEXT")  # Calendar ID (default = 'primary')
    
    # Usage tracking migrations
    add_column_if_missing(conn, "call_usage", "revenue_usd", "REAL DEFAULT 0.0")
    add_column_if_missing(conn, "call_usage", "profit_usd", "REAL DEFAULT 0.0")
    add_column_if_missing(conn, "monthly_usage", "total_revenue_usd", "REAL DEFAULT 0.0")
    add_column_if_missing(conn, "monthly_usage", "total_profit_usd", "REAL DEFAULT 0.0")
    
    conn.commit()
    conn.close()

def get_tenant_by_number(phone):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute(
        "SELECT id, phone_number FROM tenants WHERE phone_number = ?",
        (phone,)
    )

    row = cur.fetchone()
    conn.close()
    return row


def get_agent_prompt(tenant_id):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute(
        "SELECT agent_prompt FROM tenants WHERE id = ?",
        (tenant_id,)
    )

    row = cur.fetchone()
    conn.close()
    return row[0] if row else None


def set_agent_prompt(tenant_id, prompt):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute(
        "UPDATE tenants SET agent_prompt = ? WHERE id = ?",
        (prompt, tenant_id)
    )

    conn.commit()
    conn.close()

 
def create_tenant_if_missing(phone_number: str):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute(
        "INSERT OR IGNORE INTO tenants (phone_number, agent_prompt) VALUES (?, ?)",
        (phone_number, "")
    )

    conn.commit()
    conn.close()


# --- AUTH HELPERS (customer login) ---
import bcrypt

def create_user(email: str, password: str, tenant_phone: str | None = None):
    password_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO users (email, password_hash, tenant_phone) VALUES (?, ?, ?)",
        (email.strip().lower(), password_hash, tenant_phone),
    )
    conn.commit()
    conn.close()

def get_user_by_email(email: str):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "SELECT id, email, password_hash, tenant_phone FROM users WHERE email = ?",
        (email.strip().lower(),),
    )
    row = cur.fetchone()
    conn.close()
    return row  # (id, email, password_hash, tenant_phone) or None

def verify_user(email: str, password: str):
    row = get_user_by_email(email)
    if not row:
        return None
    user_id, user_email, password_hash, tenant_phone = row
    ok = bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    if not ok:
        return None
    return {
        "id": user_id,
        "email": user_email,
        "tenant_phone": tenant_phone
    }

def create_agent(
    owner_user_id: int,
    name: str,
    phone_number: str = None,
    system_prompt: str = "",
    business_name: str = None,
    voice: str = None,
    provider: str = None,
    first_message: str = None,
    tools: dict = None,   # example: {"google_calendar": True, "slack": False}
):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    tools_json = json.dumps(tools or {})

    cur.execute(
        """
        INSERT INTO agents (
            owner_user_id,
            name,
            business_name,
            phone_number,
            system_prompt,
            voice,
            provider,
            first_message,
            tools_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            owner_user_id,
            name,
            business_name,
            phone_number,
            system_prompt,
            voice,
            provider,
            first_message,
            tools_json,
        )
    )

    conn.commit()
    agent_id = cur.lastrowid
    conn.close()
    return agent_id

def list_agents(owner_user_id: int):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute(
        """
        SELECT
            id,
            name,
            business_name,
            phone_number,
            system_prompt,
            voice,
            provider,
            first_message,
            tools_json,
            created_at,
            updated_at
        FROM agents
        WHERE owner_user_id = ?
        ORDER BY id DESC
        """,
        (owner_user_id,)
    )

    rows = cur.fetchall()
    conn.close()

    agents = []
    for r in rows:
        tools_raw = r[8] or "{}"
        try:
            tools = json.loads(tools_raw)
        except Exception:
            tools = {}

        agents.append({
            "id": r[0],
            "name": r[1],
            "business_name": r[2],
            "phone_number": r[3],
            "system_prompt": r[4],
            "voice": r[5],
            "provider": r[6],
            "first_message": r[7],
            "tools": tools,          # returned as dict
            "created_at": r[9],
            "updated_at": r[10],
        })

    return agents

def get_agent(owner_user_id: int, agent_id: int):
    conn = get_conn()  # Uses row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute(
        """
        SELECT
            id, owner_user_id, name, business_name, phone_number,
            system_prompt, voice, provider, first_message, tools_json,
            created_at, updated_at
        FROM agents
        WHERE id = ? AND owner_user_id = ?
        """,
        (agent_id, owner_user_id)
    )

    row = cur.fetchone()
    conn.close()

    if not row:
        return None

    # Convert Row to dict
    agent_dict = dict(row)
    
    # Parse tools_json if present
    tools_raw = agent_dict.get("tools_json") or "{}"
    try:
        agent_dict["tools"] = json.loads(tools_raw)
    except Exception:
        agent_dict["tools"] = {}

    return agent_dict

def update_agent(owner_user_id: int, agent_id: int, **fields):
    # Allowed fields that can be updated from the UI
    allowed = {
        "name",
        "business_name",
        "phone_number",
        "system_prompt",
        "voice",
        "provider",
        "first_message",
        "tools_json",   # store JSON string
    }

    updates = {k: v for k, v in fields.items() if k in allowed and v is not None}

    # If UI passes tools as dict, convert to tools_json string
    if "tools" in fields and fields["tools"] is not None:
        updates["tools_json"] = json.dumps(fields["tools"])

    if not updates:
        return False  # nothing to update

    set_clause = ", ".join([f"{k} = ?" for k in updates.keys()])
    params = list(updates.values())
    params += [agent_id, owner_user_id]

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute(
        f"""
        UPDATE agents
        SET {set_clause},
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ? AND owner_user_id = ?
        """,
        params
    )

    conn.commit()
    changed = cur.rowcount > 0
    conn.close()
    return changed

def delete_agent(owner_user_id: int, agent_id: int):
    """Delete an agent. Only the owner can delete their own agents."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    
    cur.execute(
        "DELETE FROM agents WHERE id = ? AND owner_user_id = ?",
        (agent_id, owner_user_id)
    )
    
    conn.commit()
    deleted = cur.rowcount > 0
    conn.close()
    return deleted


# ========== Usage Tracking Functions ==========

def start_call_tracking(user_id: int, agent_id: int, call_sid: str, call_from: str, call_to: str):
    """Start tracking a new call"""
    conn = get_conn()
    cur = conn.cursor()
    
    cur.execute("""
        INSERT INTO call_usage (user_id, agent_id, call_sid, call_from, call_to, status)
        VALUES (?, ?, ?, ?, ?, 'active')
    """, (user_id, agent_id, call_sid, call_from, call_to))
    
    conn.commit()
    call_id = cur.lastrowid
    conn.close()
    
    return call_id


def end_call_tracking(call_sid: str, duration_seconds: int, cost_usd: float, revenue_usd: float):
    """End call tracking and calculate cost, revenue, and profit"""
    conn = get_conn()
    cur = conn.cursor()
    
    profit_usd = revenue_usd - cost_usd
    
    cur.execute("""
        UPDATE call_usage 
        SET duration_seconds = ?,
            cost_usd = ?,
            revenue_usd = ?,
            profit_usd = ?,
            ended_at = CURRENT_TIMESTAMP,
            status = 'completed'
        WHERE call_sid = ?
    """, (duration_seconds, cost_usd, revenue_usd, profit_usd, call_sid))
    
    # Get user_id for monthly summary
    cur.execute("SELECT user_id FROM call_usage WHERE call_sid = ?", (call_sid,))
    row = cur.fetchone()
    
    if row:
        user_id = row[0]
        month = datetime.now().strftime("%Y-%m")
        minutes = duration_seconds / 60.0
        
        # Update monthly summary
        cur.execute("""
            INSERT INTO monthly_usage (user_id, month, total_calls, total_minutes, total_cost_usd, total_revenue_usd, total_profit_usd)
            VALUES (?, ?, 1, ?, ?, ?, ?)
            ON CONFLICT(user_id, month) DO UPDATE SET
                total_calls = total_calls + 1,
                total_minutes = total_minutes + ?,
                total_cost_usd = total_cost_usd + ?,
                total_revenue_usd = total_revenue_usd + ?,
                total_profit_usd = total_profit_usd + ?
        """, (user_id, month, minutes, cost_usd, revenue_usd, profit_usd, minutes, cost_usd, revenue_usd, profit_usd))
    
    conn.commit()
    conn.close()


def get_user_usage(user_id: int, month: str = None):
    """Get usage statistics for a user"""
    conn = get_conn()
    cur = conn.cursor()
    
    if not month:
        month = datetime.now().strftime("%Y-%m")
    
    # Get monthly summary
    cur.execute("""
        SELECT total_calls, total_minutes, total_cost_usd, total_revenue_usd, total_profit_usd
        FROM monthly_usage
        WHERE user_id = ? AND month = ?
    """, (user_id, month))
    
    row = cur.fetchone()
    
    if row:
        result = {
            "month": month,
            "total_calls": row[0],
            "total_minutes": round(row[1], 2),
            "total_cost_usd": round(row[2], 4),
            "total_revenue_usd": round(row[3], 2),
            "total_profit_usd": round(row[4], 2)
        }
    else:
        result = {
            "month": month,
            "total_calls": 0,
            "total_minutes": 0.0,
            "total_cost_usd": 0.0,
            "total_revenue_usd": 0.0,
            "total_profit_usd": 0.0
        }
    
    conn.close()
    return result


def get_call_history(user_id: int, limit: int = 50):
    """Get recent call history for a user"""
    conn = get_conn()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    
    cur.execute("""
        SELECT c.*, a.name as agent_name
        FROM call_usage c
        LEFT JOIN agents a ON c.agent_id = a.id
        WHERE c.user_id = ?
        ORDER BY c.started_at DESC
        LIMIT ?
    """, (user_id, limit))
    
    calls = [dict(row) for row in cur.fetchall()]
    conn.close()
    
    return calls


def calculate_call_cost(duration_seconds: int, cost_per_minute: float = 0.05) -> float:
    """Calculate YOUR cost based on duration"""
    minutes = duration_seconds / 60.0
    return round(minutes * cost_per_minute, 4)


def calculate_call_revenue(duration_seconds: int, revenue_per_minute: float = 0.25) -> float:
    """Calculate revenue to charge customer (5x your cost)"""
    minutes = duration_seconds / 60.0
    return round(minutes * revenue_per_minute, 4)


def calculate_call_profit(cost_usd: float, revenue_usd: float) -> float:
    """Calculate profit (revenue - cost)"""
    return round(revenue_usd - cost_usd, 4)


# ========== Credits System ==========

def get_user_credits(user_id: int):
    """Get user's current credit balance"""
    conn = get_conn()
    cur = conn.cursor()
    
    cur.execute("""
        SELECT balance, total_purchased, total_used
        FROM user_credits
        WHERE user_id = ?
    """, (user_id,))
    
    row = cur.fetchone()
    
    if row:
        result = {
            "balance": round(row[0], 2),
            "total_purchased": round(row[1], 2),
            "total_used": round(row[2], 2)
        }
    else:
        # Initialize credits for new user
        cur.execute("""
            INSERT INTO user_credits (user_id, balance, total_purchased, total_used)
            VALUES (?, 0.0, 0.0, 0.0)
        """, (user_id,))
        conn.commit()
        result = {
            "balance": 0.0,
            "total_purchased": 0.0,
            "total_used": 0.0
        }
    
    conn.close()
    return result


def add_credits(user_id: int, amount: float, description: str = "Credit purchase"):
    """Add credits to user's account (when they buy credits)"""
    conn = get_conn()
    cur = conn.cursor()
    
    # Get or create user credits
    get_user_credits(user_id)
    
    # Update balance
    cur.execute("""
        UPDATE user_credits
        SET balance = balance + ?,
            total_purchased = total_purchased + ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE user_id = ?
    """, (amount, amount, user_id))
    
    # Get new balance
    cur.execute("SELECT balance FROM user_credits WHERE user_id = ?", (user_id,))
    new_balance = cur.fetchone()[0]
    
    # Record transaction
    cur.execute("""
        INSERT INTO credit_transactions (user_id, amount, type, description, balance_after)
        VALUES (?, ?, 'purchase', ?, ?)
    """, (user_id, amount, description, new_balance))
    
    conn.commit()
    conn.close()
    
    return new_balance


def deduct_credits(user_id: int, amount: float, call_id: int = None, description: str = "Call usage"):
    """Deduct credits from user's account (when they use the service)"""
    conn = get_conn()
    cur = conn.cursor()
    
    # Check balance
    cur.execute("SELECT balance FROM user_credits WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    
    if not row:
        conn.close()
        return {"success": False, "error": "No credit account found"}
    
    current_balance = row[0]
    
    if current_balance < amount:
        conn.close()
        return {"success": False, "error": "Insufficient credits", "balance": current_balance}
    
    # Deduct credits
    new_balance = current_balance - amount
    
    cur.execute("""
        UPDATE user_credits
        SET balance = ?,
            total_used = total_used + ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE user_id = ?
    """, (new_balance, amount, user_id))
    
    # Record transaction
    cur.execute("""
        INSERT INTO credit_transactions (user_id, amount, type, description, balance_after, call_id)
        VALUES (?, ?, 'usage', ?, ?, ?)
    """, (user_id, -amount, description, new_balance, call_id))
    
    conn.commit()
    conn.close()
    
    return {"success": True, "balance": new_balance, "deducted": amount}


def get_credit_transactions(user_id: int, limit: int = 50):
    """Get credit transaction history"""
    conn = get_conn()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    
    cur.execute("""
        SELECT *
        FROM credit_transactions
        WHERE user_id = ?
        ORDER BY created_at DESC
        LIMIT ?
    """, (user_id, limit))
    
    transactions = [dict(row) for row in cur.fetchall()]
    conn.close()
    
    return transactions


def check_credits_available(user_id: int, required_amount: float) -> bool:
    """Check if user has enough credits"""
    credits = get_user_credits(user_id)
    return credits["balance"] >= required_amount

def get_agent_by_id(agent_id: int):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM agents WHERE id = ?", (agent_id,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None

def get_agent_by_phone(phone_number: str):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM agents WHERE phone_number = ? LIMIT 1", (phone_number,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None
