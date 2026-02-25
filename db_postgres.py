import os
import json
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime

# Get database URL from environment
DATABASE_URL = os.getenv("DATABASE_URL")

def get_conn():
    """Get PostgreSQL connection"""
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    return conn

def init_db():
    """Initialize PostgreSQL database with all tables"""
    conn = get_conn()
    cur = conn.cursor()

    # Users table
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id SERIAL PRIMARY KEY,
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        tenant_phone TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # Agents table
    cur.execute("""
    CREATE TABLE IF NOT EXISTS agents (
        id SERIAL PRIMARY KEY,
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
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(owner_user_id) REFERENCES users(id) ON DELETE CASCADE
    )
    """)

    # Call usage table
    cur.execute("""
    CREATE TABLE IF NOT EXISTS call_usage (
        id SERIAL PRIMARY KEY,
        user_id INTEGER NOT NULL,
        agent_id INTEGER NOT NULL,
        call_sid TEXT,
        call_from TEXT,
        call_to TEXT,
        duration_seconds INTEGER DEFAULT 0,
        cost_usd NUMERIC(10,4) DEFAULT 0.0,
        revenue_usd NUMERIC(10,4) DEFAULT 0.0,
        profit_usd NUMERIC(10,4) DEFAULT 0.0,
        started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        ended_at TIMESTAMP,
        status TEXT DEFAULT 'active',
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
        FOREIGN KEY(agent_id) REFERENCES agents(id) ON DELETE CASCADE
    )
    """)

    # Monthly usage table
    cur.execute("""
    CREATE TABLE IF NOT EXISTS monthly_usage (
        id SERIAL PRIMARY KEY,
        user_id INTEGER NOT NULL,
        month TEXT NOT NULL,
        total_calls INTEGER DEFAULT 0,
        total_minutes NUMERIC(10,2) DEFAULT 0.0,
        total_cost_usd NUMERIC(10,4) DEFAULT 0.0,
        total_revenue_usd NUMERIC(10,4) DEFAULT 0.0,
        total_profit_usd NUMERIC(10,4) DEFAULT 0.0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
        UNIQUE(user_id, month)
    )
    """)

    # Credits balance table
    cur.execute("""
    CREATE TABLE IF NOT EXISTS user_credits (
        id SERIAL PRIMARY KEY,
        user_id INTEGER NOT NULL UNIQUE,
        balance NUMERIC(10,2) DEFAULT 0.0,
        total_purchased NUMERIC(10,2) DEFAULT 0.0,
        total_used NUMERIC(10,2) DEFAULT 0.0,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
    )
    """)

    # Credit transactions table
    cur.execute("""
    CREATE TABLE IF NOT EXISTS credit_transactions (
        id SERIAL PRIMARY KEY,
        user_id INTEGER NOT NULL,
        amount NUMERIC(10,4) NOT NULL,
        type TEXT NOT NULL,
        description TEXT,
        balance_after NUMERIC(10,2) NOT NULL,
        call_id INTEGER,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
        FOREIGN KEY(call_id) REFERENCES call_usage(id) ON DELETE SET NULL
    )
    """)

    # Create indexes for performance
    cur.execute("CREATE INDEX IF NOT EXISTS idx_agents_owner ON agents(owner_user_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_agents_phone ON agents(phone_number)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_call_usage_user ON call_usage(user_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_call_usage_agent ON call_usage(agent_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_credit_tx_user ON credit_transactions(user_id)")

    conn.commit()
    cur.close()
    conn.close()
    
    print("✅ PostgreSQL database initialized successfully")


# Note: All other functions (get_agent_by_id, create_agent, etc.) work the same
# Just need to replace sqlite3 with psycopg2 connection
# The SQL queries are mostly compatible, just minor syntax differences
