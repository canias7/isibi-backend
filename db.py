import os
import json
from datetime import datetime

# Check which database to use
DATABASE_URL = os.getenv("DATABASE_URL")
USE_POSTGRES = DATABASE_URL and DATABASE_URL.startswith("postgres")

if USE_POSTGRES:
    try:
        import psycopg2
        from psycopg2.extras import RealDictCursor
        import sqlite3  # Still import for the exception types
        
        def get_conn():
            conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
            return conn
        
        PH = "%s"  # SQL placeholder for PostgreSQL
        
        def sql(query):
            """Replace {PH} placeholders in query string"""
            return query.replace("{PH}", PH)
        
        print("✅ Using PostgreSQL database")
    except ImportError as e:
        print(f"⚠️ PostgreSQL import failed: {e}")
        print("⚠️ Falling back to SQLite")
        USE_POSTGRES = False
        import sqlite3
        
        DB_PATH = os.getenv("DB_PATH", "app.db")
        
        def get_conn():
            conn = sqlite3.connect(DB_PATH, timeout=30, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA busy_timeout=30000;")
            return conn
        
        PH = "?"  # SQL placeholder for SQLite
        
        def sql(query):
            """Replace {PH} placeholders in query string"""
            return query.replace("{PH}", PH)
else:
    import sqlite3
    
    DB_PATH = os.getenv("DB_PATH", "app.db")
    
    def get_conn():
        conn = sqlite3.connect(DB_PATH, timeout=30, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA busy_timeout=30000;")
        return conn
    
    PH = "?"  # SQL placeholder for SQLite
    
    def sql(query):
        """Replace {PH} placeholders in query string"""
        return query.replace("{PH}", PH)
    
    print("⚠️ Using SQLite database (local dev)")
    
    # SQL placeholder for SQLite
    def sql_placeholder():
        return "?"
    
    print("⚠️ Using SQLite database (local dev)")

def add_column_if_missing(conn, table, column, coltype):
    """Add column to table if it doesn't exist - works with both SQLite and PostgreSQL"""
    cur = conn.cursor()
    
    if USE_POSTGRES:
        # PostgreSQL: Check information_schema
        cur.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = %s AND column_name = %s
        """, (table, column))
        exists = cur.fetchone() is not None
        
        if not exists:
            cur.execute(f"ALTER TABLE {table} ADD COLUMN {column} {coltype}")
            conn.commit()
    else:
        # SQLite: Use PRAGMA
        cur.execute(f"PRAGMA table_info({table})")
        cols = [row[1] for row in cur.fetchall()]
        if column not in cols:
            cur.execute(f"ALTER TABLE {table} ADD COLUMN {column} {coltype}")
            conn.commit()

def init_db():
    conn = get_conn()
    cur = conn.cursor()
    
    # Determine SQL syntax based on database type
    if USE_POSTGRES:
        # PostgreSQL syntax
        ID = "SERIAL PRIMARY KEY"
        REAL = "NUMERIC(10,4)"
        TIMESTAMP = "TIMESTAMP"
    else:
        # SQLite syntax
        ID = "INTEGER PRIMARY KEY AUTOINCREMENT"
        REAL = "REAL"
        TIMESTAMP = "TEXT"

    cur.execute(f"""
    CREATE TABLE IF NOT EXISTS tenants (
        id {ID},
        phone_number TEXT UNIQUE,
        agent_prompt TEXT
    )
    """)
    
    cur.execute(f"""
    CREATE TABLE IF NOT EXISTS users (
        id {ID},
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        tenant_phone TEXT,
        created_at {TIMESTAMP} DEFAULT CURRENT_TIMESTAMP
    )
    """)
    
    cur.execute(f"""
    CREATE TABLE IF NOT EXISTS agents (
        id {ID},
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
        twilio_number_sid TEXT,
        deleted_at {TIMESTAMP},
        created_at {TIMESTAMP} DEFAULT CURRENT_TIMESTAMP,
        updated_at {TIMESTAMP} DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(owner_user_id) REFERENCES users(id)
    )
    """)
    
    # Add deleted_at column if it doesn't exist (migration)
    add_column_if_missing(conn, 'agents', 'deleted_at', f'{TIMESTAMP}')
    
    # Add twilio_number_sid column if it doesn't exist (migration)
    add_column_if_missing(conn, 'agents', 'twilio_number_sid', 'TEXT')
    
    # Add detailed cost breakdown columns to call_usage (migration)
    add_column_if_missing(conn, 'call_usage', 'input_tokens', 'INTEGER DEFAULT 0')
    add_column_if_missing(conn, 'call_usage', 'output_tokens', 'INTEGER DEFAULT 0')
    add_column_if_missing(conn, 'call_usage', 'input_audio_minutes', f'{REAL} DEFAULT 0.0')
    add_column_if_missing(conn, 'call_usage', 'output_audio_minutes', f'{REAL} DEFAULT 0.0')
    add_column_if_missing(conn, 'call_usage', 'cost_input_tokens', f'{REAL} DEFAULT 0.0')
    add_column_if_missing(conn, 'call_usage', 'cost_output_tokens', f'{REAL} DEFAULT 0.0')
    add_column_if_missing(conn, 'call_usage', 'cost_input_audio', f'{REAL} DEFAULT 0.0')
    add_column_if_missing(conn, 'call_usage', 'cost_output_audio', f'{REAL} DEFAULT 0.0')
    add_column_if_missing(conn, 'call_usage', 'cost_twilio_phone', f'{REAL} DEFAULT 0.0')
    add_column_if_missing(conn, 'call_usage', 'revenue_input_tokens', f'{REAL} DEFAULT 0.0')
    add_column_if_missing(conn, 'call_usage', 'revenue_output_tokens', f'{REAL} DEFAULT 0.0')
    add_column_if_missing(conn, 'call_usage', 'revenue_input_audio', f'{REAL} DEFAULT 0.0')
    add_column_if_missing(conn, 'call_usage', 'revenue_output_audio', f'{REAL} DEFAULT 0.0')
    add_column_if_missing(conn, 'call_usage', 'revenue_twilio_phone', f'{REAL} DEFAULT 0.0')
    
    # Add partial unique index for phone numbers (only for non-deleted agents)
    if USE_POSTGRES:
        try:
            cur.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS agents_phone_active_unique 
                ON agents (phone_number) 
                WHERE deleted_at IS NULL AND phone_number IS NOT NULL
            """)
        except:
            pass  # Index might already exist
    
    # Usage tracking table
    cur.execute(f"""
    CREATE TABLE IF NOT EXISTS call_usage (
        id {ID},
        user_id INTEGER NOT NULL,
        agent_id INTEGER NOT NULL,
        call_sid TEXT,
        call_from TEXT,
        call_to TEXT,
        duration_seconds INTEGER DEFAULT 0,
        cost_usd {REAL} DEFAULT 0.0,
        revenue_usd {REAL} DEFAULT 0.0,
        profit_usd {REAL} DEFAULT 0.0,
        started_at {TIMESTAMP} DEFAULT CURRENT_TIMESTAMP,
        ended_at {TIMESTAMP},
        status TEXT DEFAULT 'active',
        
        -- Detailed cost breakdown
        input_tokens INTEGER DEFAULT 0,
        output_tokens INTEGER DEFAULT 0,
        input_audio_minutes {REAL} DEFAULT 0.0,
        output_audio_minutes {REAL} DEFAULT 0.0,
        
        -- Cost components (what YOU pay)
        cost_input_tokens {REAL} DEFAULT 0.0,
        cost_output_tokens {REAL} DEFAULT 0.0,
        cost_input_audio {REAL} DEFAULT 0.0,
        cost_output_audio {REAL} DEFAULT 0.0,
        cost_twilio_phone {REAL} DEFAULT 0.0,
        
        -- Revenue components (what CUSTOMER pays)
        revenue_input_tokens {REAL} DEFAULT 0.0,
        revenue_output_tokens {REAL} DEFAULT 0.0,
        revenue_input_audio {REAL} DEFAULT 0.0,
        revenue_output_audio {REAL} DEFAULT 0.0,
        revenue_twilio_phone {REAL} DEFAULT 0.0,
        
        FOREIGN KEY(user_id) REFERENCES users(id),
        FOREIGN KEY(agent_id) REFERENCES agents(id)
    )
    """)
    
    # Monthly usage summary table
    cur.execute(f"""
    CREATE TABLE IF NOT EXISTS monthly_usage (
        id {ID},
        user_id INTEGER NOT NULL,
        month TEXT NOT NULL,
        total_calls INTEGER DEFAULT 0,
        total_minutes {REAL} DEFAULT 0.0,
        total_cost_usd {REAL} DEFAULT 0.0,
        total_revenue_usd {REAL} DEFAULT 0.0,
        total_profit_usd {REAL} DEFAULT 0.0,
        created_at {TIMESTAMP} DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(user_id) REFERENCES users(id),
        UNIQUE(user_id, month)
    )
    """)
    
    # Credits balance table
    cur.execute(f"""
    CREATE TABLE IF NOT EXISTS user_credits (
        id {ID},
        user_id INTEGER NOT NULL UNIQUE,
        balance {REAL} DEFAULT 0.0,
        total_purchased {REAL} DEFAULT 0.0,
        total_used {REAL} DEFAULT 0.0,
        updated_at {TIMESTAMP} DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(user_id) REFERENCES users(id)
    )
    """)
    
    # Credit transactions table
    cur.execute(f"""
    CREATE TABLE IF NOT EXISTS credit_transactions (
        id {ID},
        user_id INTEGER NOT NULL,
        amount {REAL} NOT NULL,
        type TEXT NOT NULL,
        description TEXT,
        balance_after {REAL} NOT NULL,
        call_id INTEGER,
        created_at {TIMESTAMP} DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(user_id) REFERENCES users(id),
        FOREIGN KEY(call_id) REFERENCES call_usage(id)
    )
    """)
    
    # User-level Google credentials
    cur.execute(f"""
    CREATE TABLE IF NOT EXISTS user_google_credentials (
        id {ID},
        user_id INTEGER NOT NULL UNIQUE,
        google_calendar_credentials TEXT,
        google_calendar_id TEXT DEFAULT 'primary',
        created_at {TIMESTAMP} DEFAULT CURRENT_TIMESTAMP,
        updated_at {TIMESTAMP} DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(user_id) REFERENCES users(id)
    )
    """)
    
    # Pricing plans table
    cur.execute(f"""
    CREATE TABLE IF NOT EXISTS pricing_plans (
        id {ID},
        name TEXT NOT NULL,
        price_per_minute {REAL} NOT NULL,
        included_minutes INTEGER DEFAULT 0,
        monthly_fee {REAL} DEFAULT 0.0,
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
    
    # Slack integration columns
    add_column_if_missing(conn, "users", "slack_bot_token", "TEXT")
    add_column_if_missing(conn, "users", "slack_default_channel", "TEXT")
    add_column_if_missing(conn, "users", "slack_enabled", "BOOLEAN DEFAULT FALSE")
    add_column_if_missing(conn, "agents", "slack_channel", "TEXT")  # Per-agent channel override
    
    # Microsoft Teams integration columns
    add_column_if_missing(conn, "users", "teams_webhook_url", "TEXT")
    add_column_if_missing(conn, "users", "teams_enabled", "BOOLEAN DEFAULT FALSE")
    
    # Usage tracking migrations
    add_column_if_missing(conn, "call_usage", "revenue_usd", "REAL DEFAULT 0.0")
    add_column_if_missing(conn, "call_usage", "profit_usd", "REAL DEFAULT 0.0")
    add_column_if_missing(conn, "monthly_usage", "total_revenue_usd", "REAL DEFAULT 0.0")
    add_column_if_missing(conn, "monthly_usage", "total_profit_usd", "REAL DEFAULT 0.0")
    
    conn.commit()
    conn.close()

def get_tenant_by_number(phone):
    conn = get_conn()
    cur = conn.cursor()

    cur.execute(
        sql("SELECT id, phone_number FROM tenants WHERE phone_number = {PH}"),
        (phone,)
    )

    row = cur.fetchone()
    conn.close()
    return row


def get_agent_prompt(tenant_id):
    conn = get_conn()
    cur = conn.cursor()

    cur.execute(
        sql("SELECT agent_prompt FROM tenants WHERE id = {PH}"),
        (tenant_id,)
    )

    row = cur.fetchone()
    conn.close()
    return row[0] if row else None


def set_agent_prompt(tenant_id, prompt):
    conn = get_conn()
    cur = conn.cursor()

    cur.execute(
        sql("UPDATE tenants SET agent_prompt = {PH} WHERE id = {PH}"),
        (prompt, tenant_id)
    )

    conn.commit()
    conn.close()

 
def create_tenant_if_missing(phone_number: str):
    conn = get_conn()
    cur = conn.cursor()

    if USE_POSTGRES:
        # PostgreSQL syntax
        cur.execute(
            sql("INSERT INTO tenants (phone_number, agent_prompt) VALUES ({PH}, {PH}) ON CONFLICT (phone_number) DO NOTHING"),
            (phone_number, "")
        )
    else:
        # SQLite syntax
        cur.execute(
            sql("INSERT OR IGNORE INTO tenants (phone_number, agent_prompt) VALUES ({PH}, {PH})"),
            (phone_number, "")
        )

    conn.commit()
    conn.close()


# --- AUTH HELPERS (customer login) ---
import bcrypt

def create_user(email: str, password: str, tenant_phone: str | None = None):
    password_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        sql("INSERT INTO users (email, password_hash, tenant_phone) VALUES ({PH}, {PH}, {PH})"),
        (email.strip().lower(), password_hash, tenant_phone),
    )
    conn.commit()
    conn.close()

def get_user_by_email(email: str):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        sql("SELECT id, email, password_hash, tenant_phone FROM users WHERE email = {PH}"),
        (email.strip().lower(),),
    )
    row = cur.fetchone()
    conn.close()
    return row  # (id, email, password_hash, tenant_phone) or None

def verify_user(email: str, password: str):
    row = get_user_by_email(email)
    if not row:
        return None
    
    # Handle both SQLite (tuple) and PostgreSQL (dict) row formats
    if isinstance(row, dict):
        user_id = row['id']
        user_email = row['email']
        password_hash = row['password_hash']
        tenant_phone = row.get('tenant_phone')
    else:
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
    twilio_number_sid: str = None,
):
    conn = get_conn()
    cur = conn.cursor()

    tools_json = json.dumps(tools or {})

    cur.execute(
        sql("""
        INSERT INTO agents (
            owner_user_id,
            name,
            business_name,
            phone_number,
            system_prompt,
            voice,
            provider,
            first_message,
            tools_json,
            twilio_number_sid
        )
        VALUES ({PH}, {PH}, {PH}, {PH}, {PH}, {PH}, {PH}, {PH}, {PH}, {PH})
        """ + (" RETURNING id" if USE_POSTGRES else "")),
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
            twilio_number_sid,
        )
    )

    if USE_POSTGRES:
        row = cur.fetchone()
        agent_id = row['id'] if isinstance(row, dict) else row[0]
    else:
        agent_id = cur.lastrowid
    
    conn.commit()
    conn.close()
    return agent_id

def list_agents(owner_user_id: int):
    conn = get_conn()
    cur = conn.cursor()

    cur.execute(
        sql("""
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
        WHERE owner_user_id = {PH} AND deleted_at IS NULL
        ORDER BY id DESC
        """),
        (owner_user_id,)
    )

    rows = cur.fetchall()
    conn.close()

    agents = []
    for r in rows:
        # Handle both SQLite (tuple/list) and PostgreSQL (dict) formats
        if isinstance(r, dict):
            tools_raw = r.get('tools_json') or "{}"
            agent_dict = {
                "id": r['id'],
                "name": r['name'],
                "business_name": r.get('business_name'),
                "phone_number": r.get('phone_number'),
                "system_prompt": r.get('system_prompt'),
                "voice": r.get('voice'),
                "provider": r.get('provider'),
                "first_message": r.get('first_message'),
                "created_at": str(r.get('created_at')) if r.get('created_at') else None,
                "updated_at": str(r.get('updated_at')) if r.get('updated_at') else None,
            }
        else:
            # SQLite tuple format
            tools_raw = r[8] or "{}"
            agent_dict = {
                "id": r[0],
                "name": r[1],
                "business_name": r[2],
                "phone_number": r[3],
                "system_prompt": r[4],
                "voice": r[5],
                "provider": r[6],
                "first_message": r[7],
                "created_at": r[9],
                "updated_at": r[10],
            }
        
        try:
            tools = json.loads(tools_raw)
        except Exception:
            tools = {}

        agent_dict["tools"] = tools
        agents.append(agent_dict)

    return agents

def get_agent(owner_user_id: int, agent_id: int):
    conn = get_conn()  # Uses row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute(
        sql("""
        SELECT
            id, owner_user_id, name, business_name, phone_number,
            system_prompt, voice, provider, first_message, tools_json,
            created_at, updated_at
        FROM agents
        WHERE id = {PH} AND owner_user_id = {PH} AND deleted_at IS NULL
        """),
        (agent_id, owner_user_id)
    )

    row = cur.fetchone()
    conn.close()

    if not row:
        return None

    # Convert Row to dict
    agent_dict = dict(row)
    
    # Convert datetime objects to strings for PostgreSQL
    if agent_dict.get("created_at") and not isinstance(agent_dict["created_at"], str):
        agent_dict["created_at"] = str(agent_dict["created_at"])
    if agent_dict.get("updated_at") and not isinstance(agent_dict["updated_at"], str):
        agent_dict["updated_at"] = str(agent_dict["updated_at"])
    
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

    set_clause = ", ".join([f"{k} = {{PH}}" for k in updates.keys()])
    params = list(updates.values())
    params += [agent_id, owner_user_id]

    conn = get_conn()
    cur = conn.cursor()

    query = f"""
        UPDATE agents
        SET {set_clause},
            updated_at = CURRENT_TIMESTAMP
        WHERE id = {{PH}} AND owner_user_id = {{PH}} AND deleted_at IS NULL
    """
    
    cur.execute(sql(query), params)

    conn.commit()
    changed = cur.rowcount > 0
    conn.close()
    return changed

def delete_agent(owner_user_id: int, agent_id: int):
    """
    Soft delete an agent (marks as deleted but keeps for historical call data).
    Only the owner can delete their own agents.
    """
    conn = get_conn()
    cur = conn.cursor()
    
    # Soft delete - set deleted_at timestamp instead of actual deletion
    cur.execute(
        sql("UPDATE agents SET deleted_at = CURRENT_TIMESTAMP WHERE id = {PH} AND owner_user_id = {PH} AND deleted_at IS NULL"),
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
    
    if USE_POSTGRES:
        # PostgreSQL - use RETURNING to get the ID
        cur.execute(sql("""
            INSERT INTO call_usage (user_id, agent_id, call_sid, call_from, call_to, status)
            VALUES ({PH}, {PH}, {PH}, {PH}, {PH}, 'active')
            RETURNING id
        """), (user_id, agent_id, call_sid, call_from, call_to))
        row = cur.fetchone()
        call_id = row['id'] if isinstance(row, dict) else row[0]
    else:
        # SQLite - use lastrowid
        cur.execute(sql("""
            INSERT INTO call_usage (user_id, agent_id, call_sid, call_from, call_to, status)
            VALUES ({PH}, {PH}, {PH}, {PH}, {PH}, 'active')
        """), (user_id, agent_id, call_sid, call_from, call_to))
        call_id = cur.lastrowid
    
    conn.commit()
    conn.close()
    
    return call_id


def end_call_tracking(call_sid: str, duration_seconds: int, cost_usd: float, revenue_usd: float, 
                     usage_details: dict = None):
    """
    End call tracking and calculate cost, revenue, and profit
    
    usage_details can include:
    {
        "input_tokens": 1000,
        "output_tokens": 2000,
        "input_audio_seconds": 120,
        "output_audio_seconds": 130
    }
    """
    conn = get_conn()
    cur = conn.cursor()
    
    profit_usd = revenue_usd - cost_usd
    
    # Default empty usage details if not provided
    if not usage_details:
        usage_details = {}
    
    # Extract usage metrics
    input_tokens = usage_details.get('input_tokens', 0)
    output_tokens = usage_details.get('output_tokens', 0)
    input_audio_seconds = usage_details.get('input_audio_seconds', 0)
    output_audio_seconds = usage_details.get('output_audio_seconds', 0)
    
    # Convert seconds to minutes for audio
    input_audio_minutes = input_audio_seconds / 60.0
    output_audio_minutes = output_audio_seconds / 60.0
    
    # OpenAI Realtime API Pricing (as of Feb 2025)
    # Text: $5/1M input tokens, $20/1M output tokens
    # Audio: $100/1M input tokens (~$0.06/min), $200/1M output tokens (~$0.24/min)
    # Approximations: 1 min audio ≈ 1,500 tokens
    
    # Calculate YOUR costs (what you pay OpenAI + Twilio)
    cost_input_tokens = (input_tokens / 1_000_000) * 5.0  # $5 per 1M tokens
    cost_output_tokens = (output_tokens / 1_000_000) * 20.0  # $20 per 1M tokens
    cost_input_audio = input_audio_minutes * 0.06  # ~$0.06/min
    cost_output_audio = output_audio_minutes * 0.24  # ~$0.24/min
    cost_twilio_phone = (duration_seconds / 60.0) * 0.0085  # $0.0085/min
    
    # Calculate total cost
    total_component_cost = (cost_input_tokens + cost_output_tokens + 
                           cost_input_audio + cost_output_audio + cost_twilio_phone)
    
    # Use provided cost_usd or calculated cost
    final_cost_usd = cost_usd if cost_usd > 0 else total_component_cost
    
    # Calculate CUSTOMER revenue (what you charge them) - 5x markup
    revenue_input_tokens = cost_input_tokens * 5
    revenue_output_tokens = cost_output_tokens * 5
    revenue_input_audio = cost_input_audio * 5
    revenue_output_audio = cost_output_audio * 5
    revenue_twilio_phone = cost_twilio_phone * 5
    
    # Calculate total revenue
    total_component_revenue = (revenue_input_tokens + revenue_output_tokens + 
                               revenue_input_audio + revenue_output_audio + revenue_twilio_phone)
    
    # Use provided revenue or calculated revenue
    final_revenue_usd = revenue_usd if revenue_usd > 0 else total_component_revenue
    
    # Update call record with detailed breakdown
    cur.execute(sql("""
        UPDATE call_usage 
        SET duration_seconds = {PH},
            cost_usd = {PH},
            revenue_usd = {PH},
            profit_usd = {PH},
            ended_at = CURRENT_TIMESTAMP,
            status = 'completed',
            
            input_tokens = {PH},
            output_tokens = {PH},
            input_audio_minutes = {PH},
            output_audio_minutes = {PH},
            
            cost_input_tokens = {PH},
            cost_output_tokens = {PH},
            cost_input_audio = {PH},
            cost_output_audio = {PH},
            cost_twilio_phone = {PH},
            
            revenue_input_tokens = {PH},
            revenue_output_tokens = {PH},
            revenue_input_audio = {PH},
            revenue_output_audio = {PH},
            revenue_twilio_phone = {PH}
        WHERE call_sid = {PH}
    """), (duration_seconds, final_cost_usd, final_revenue_usd, profit_usd,
           input_tokens, output_tokens, input_audio_minutes, output_audio_minutes,
           cost_input_tokens, cost_output_tokens, cost_input_audio, cost_output_audio, cost_twilio_phone,
           revenue_input_tokens, revenue_output_tokens, revenue_input_audio, revenue_output_audio, revenue_twilio_phone,
           call_sid))
    
    # Get user_id for monthly summary
    cur.execute(sql("SELECT user_id FROM call_usage WHERE call_sid = {PH}"), (call_sid,))
    row = cur.fetchone()
    
    if row:
        # Handle both dict (PostgreSQL) and tuple (SQLite)
        user_id = row['user_id'] if isinstance(row, dict) else row[0]
        month = datetime.now().strftime("%Y-%m")
        minutes = duration_seconds / 60.0
        
        # Update monthly summary
        if USE_POSTGRES:
            # PostgreSQL - use EXCLUDED prefix to avoid ambiguity
            cur.execute(sql("""
                INSERT INTO monthly_usage (user_id, month, total_calls, total_minutes, total_cost_usd, total_revenue_usd, total_profit_usd)
                VALUES ({PH}, {PH}, 1, {PH}, {PH}, {PH}, {PH})
                ON CONFLICT(user_id, month) DO UPDATE SET
                    total_calls = monthly_usage.total_calls + 1,
                    total_minutes = monthly_usage.total_minutes + {PH},
                    total_cost_usd = monthly_usage.total_cost_usd + {PH},
                    total_revenue_usd = monthly_usage.total_revenue_usd + {PH},
                    total_profit_usd = monthly_usage.total_profit_usd + {PH}
            """), (user_id, month, minutes, cost_usd, revenue_usd, profit_usd, minutes, cost_usd, revenue_usd, profit_usd))
        else:
            # SQLite - use INSERT OR REPLACE
            cur.execute(sql("""
                INSERT INTO monthly_usage (user_id, month, total_calls, total_minutes, total_cost_usd, total_revenue_usd, total_profit_usd)
                VALUES ({PH}, {PH}, 1, {PH}, {PH}, {PH}, {PH})
                ON CONFLICT(user_id, month) DO UPDATE SET
                    total_calls = total_calls + 1,
                    total_minutes = total_minutes + {PH},
                    total_cost_usd = total_cost_usd + {PH},
                    total_revenue_usd = total_revenue_usd + {PH},
                    total_profit_usd = total_profit_usd + {PH}
            """), (user_id, month, minutes, cost_usd, revenue_usd, profit_usd, minutes, cost_usd, revenue_usd, profit_usd))
    
    conn.commit()
    conn.close()


def get_user_usage(user_id: int, month: str = None):
    """Get usage statistics for a user"""
    conn = get_conn()
    cur = conn.cursor()
    
    if not month:
        month = datetime.now().strftime("%Y-%m")
    
    # Get monthly summary
    cur.execute(sql("""
        SELECT total_calls, total_minutes, total_cost_usd, total_revenue_usd, total_profit_usd
        FROM monthly_usage
        WHERE user_id = {PH} AND month = {PH}
    """), (user_id, month))
    
    row = cur.fetchone()
    
    if row:
        # Handle both dict (PostgreSQL) and tuple (SQLite)
        if isinstance(row, dict):
            result = {
                "month": month,
                "total_calls": row['total_calls'],
                "total_minutes": round(float(row['total_minutes']), 2),
                "total_cost_usd": round(float(row['total_cost_usd']), 4),
                "total_revenue_usd": round(float(row['total_revenue_usd']), 2),
                "total_profit_usd": round(float(row['total_profit_usd']), 2)
            }
        else:
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
    cur = conn.cursor()
    
    cur.execute(sql("""
        SELECT c.*, a.name as agent_name
        FROM call_usage c
        LEFT JOIN agents a ON c.agent_id = a.id
        WHERE c.user_id = {PH}
        ORDER BY c.started_at DESC
        LIMIT {PH}
    """), (user_id, limit))
    
    calls = []
    for row in cur.fetchall():
        call_dict = dict(row)
        
        # Convert datetime objects to strings for PostgreSQL
        if call_dict.get("started_at") and not isinstance(call_dict["started_at"], str):
            call_dict["started_at"] = str(call_dict["started_at"])
        if call_dict.get("ended_at") and not isinstance(call_dict["ended_at"], str):
            call_dict["ended_at"] = str(call_dict["ended_at"])
            
        calls.append(call_dict)
    
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
    
    cur.execute(sql("""
        SELECT balance, total_purchased, total_used
        FROM user_credits
        WHERE user_id = {PH}
    """), (user_id,))
    
    row = cur.fetchone()
    
    if row:
        # Handle both SQLite (tuple) and PostgreSQL (dict)
        if isinstance(row, dict):
            result = {
                "balance": round(float(row['balance']), 2),
                "total_purchased": round(float(row['total_purchased']), 2),
                "total_used": round(float(row['total_used']), 2)
            }
        else:
            result = {
                "balance": round(row[0], 2),
                "total_purchased": round(row[1], 2),
                "total_used": round(row[2], 2)
            }
        conn.close()
        return result
    
    # User doesn't have credits record yet - create one
    try:
        cur.execute(sql("""
            INSERT INTO user_credits (user_id, balance, total_purchased, total_used)
            VALUES ({PH}, 0.0, 0.0, 0.0)
        """), (user_id,))
        conn.commit()
    except sqlite3.IntegrityError:
        # Race condition - record was created by another thread
        # Just fetch it again
        cur.execute(sql("""
            SELECT balance, total_purchased, total_used
            FROM user_credits
            WHERE user_id = {PH}
        """), (user_id,))
        row = cur.fetchone()
        if row:
            if isinstance(row, dict):
                result = {
                    "balance": round(float(row['balance']), 2),
                    "total_purchased": round(float(row['total_purchased']), 2),
                    "total_used": round(float(row['total_used']), 2)
                }
            else:
                result = {
                    "balance": round(row[0], 2),
                    "total_purchased": round(row[1], 2),
                    "total_used": round(row[2], 2)
                }
            conn.close()
            return result
    
    conn.close()
    return {
        "balance": 0.0,
        "total_purchased": 0.0,
        "total_used": 0.0
    }


def add_credits(user_id: int, amount: float, description: str = "Credit purchase"):
    """Add credits to user's account (when they buy credits)"""
    conn = get_conn()
    cur = conn.cursor()
    
    # Get or create user credits
    get_user_credits(user_id)
    
    # Update balance
    cur.execute(sql("""
        UPDATE user_credits
        SET balance = balance + {PH},
            total_purchased = total_purchased + {PH},
            updated_at = CURRENT_TIMESTAMP
        WHERE user_id = {PH}
    """), (amount, amount, user_id))
    
    # Get new balance
    cur.execute(sql("SELECT balance FROM user_credits WHERE user_id = {PH}"), (user_id,))
    row = cur.fetchone()
    
    # Handle both dict and tuple
    if isinstance(row, dict):
        new_balance = float(row['balance'])
    else:
        new_balance = row[0]
    
    # Record transaction
    cur.execute(sql("""
        INSERT INTO credit_transactions (user_id, amount, type, description, balance_after)
        VALUES ({PH}, {PH}, 'purchase', {PH}, {PH})
    """), (user_id, amount, description, new_balance))
    
    conn.commit()
    conn.close()
    
    return new_balance


def deduct_credits(user_id: int, amount: float, call_id: int = None, description: str = "Call usage"):
    """Deduct credits from user's account (when they use the service)"""
    print(f"📝 deduct_credits called: user_id={user_id}, amount={amount}, description={description}")
    
    conn = get_conn()
    cur = conn.cursor()
    
    # Check balance
    cur.execute(sql("SELECT balance FROM user_credits WHERE user_id = {PH}"), (user_id,))
    row = cur.fetchone()
    
    if not row:
        print(f"❌ No credit account found for user {user_id}")
        conn.close()
        return {"success": False, "error": "No credit account found"}
    
    # Handle both dict (PostgreSQL) and tuple (SQLite)
    current_balance = float(row['balance']) if isinstance(row, dict) else row[0]
    print(f"💰 Current balance: ${current_balance:.2f}")
    
    if current_balance < amount:
        print(f"❌ Insufficient credits: has ${current_balance:.2f}, needs ${amount:.2f}")
        conn.close()
        return {"success": False, "error": "Insufficient credits", "balance": current_balance}
    
    # Deduct credits
    new_balance = current_balance - amount
    print(f"💳 Deducting ${amount:.2f}, new balance will be ${new_balance:.2f}")
    
    cur.execute(sql("""
        UPDATE user_credits
        SET balance = {PH},
            total_used = total_used + {PH},
            updated_at = CURRENT_TIMESTAMP
        WHERE user_id = {PH}
    """), (new_balance, amount, user_id))
    
    print(f"✅ Updated user_credits table, rows affected: {cur.rowcount}")
    
    # Record transaction
    cur.execute(sql("""
        INSERT INTO credit_transactions (user_id, amount, type, description, balance_after, call_id)
        VALUES ({PH}, {PH}, 'usage', {PH}, {PH}, {PH})
    """), (user_id, -amount, description, new_balance, call_id))
    
    print(f"✅ Inserted transaction record, rows affected: {cur.rowcount}")
    
    conn.commit()
    print(f"✅ Transaction committed to database")
    conn.close()
    
    return {"success": True, "balance": new_balance, "deducted": amount}


def get_credit_transactions(user_id: int, limit: int = 50):
    """Get credit transaction history"""
    conn = get_conn()
    cur = conn.cursor()
    
    cur.execute(sql("""
        SELECT *
        FROM credit_transactions
        WHERE user_id = {PH}
        ORDER BY created_at DESC
        LIMIT {PH}
    """), (user_id, limit))
    
    transactions = []
    for row in cur.fetchall():
        tx_dict = dict(row)
        
        # Convert datetime objects to strings for PostgreSQL
        if tx_dict.get("created_at") and not isinstance(tx_dict["created_at"], str):
            tx_dict["created_at"] = str(tx_dict["created_at"])
            
        transactions.append(tx_dict)
    
    conn.close()
    
    return transactions


def check_credits_available(user_id: int, required_amount: float) -> bool:
    """Check if user has enough credits"""
    credits = get_user_credits(user_id)
    return credits["balance"] >= required_amount


# ========== User-Level Google Calendar Functions ==========

def get_user_google_credentials(user_id: int):
    """Get user's Google Calendar credentials (before assigning to agent)"""
    conn = get_conn()
    cur = conn.cursor()
    
    cur.execute(sql("""
        SELECT google_calendar_credentials, google_calendar_id
        FROM user_google_credentials
        WHERE user_id = {PH}
    """), (user_id,))
    
    row = cur.fetchone()
    conn.close()
    
    if row and row[0]:
        return {
            "credentials": row[0],
            "calendar_id": row[1] or "primary"
        }
    return None


def save_user_google_credentials(user_id: int, credentials_json: str, calendar_id: str = "primary"):
    """Save Google credentials at user level (during OAuth flow)"""
    conn = get_conn()
    cur = conn.cursor()
    
    cur.execute(sql("""
        INSERT INTO user_google_credentials (user_id, google_calendar_credentials, google_calendar_id)
        VALUES ({PH}, {PH}, {PH})
        ON CONFLICT(user_id) DO UPDATE SET
            google_calendar_credentials = {PH},
            google_calendar_id = {PH},
            updated_at = CURRENT_TIMESTAMP
    """), (user_id, credentials_json, calendar_id, credentials_json, calendar_id))
    
    conn.commit()
    conn.close()


def assign_google_calendar_to_agent(user_id: int, agent_id: int):
    """Copy user's Google credentials to a specific agent"""
    # Get user credentials
    user_creds = get_user_google_credentials(user_id)
    
    if not user_creds:
        return False
    
    # Assign to agent
    conn = get_conn()
    cur = conn.cursor()
    
    cur.execute(sql("""
        UPDATE agents
        SET google_calendar_credentials = {PH},
            google_calendar_id = {PH}
        WHERE id = {PH} AND owner_user_id = {PH} AND deleted_at IS NULL
    """), (user_creds["credentials"], user_creds["calendar_id"], agent_id, user_id))
    
    conn.commit()
    changed = cur.rowcount > 0
    conn.close()
    
    return changed

def get_agent_by_id(agent_id: int):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(sql("SELECT * FROM agents WHERE id = {PH} AND deleted_at IS NULL"), (agent_id,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None

def get_agent_by_phone(phone_number: str):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(sql("SELECT * FROM agents WHERE phone_number = {PH} AND deleted_at IS NULL LIMIT 1"), (phone_number,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None
