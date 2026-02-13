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
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(owner_user_id) REFERENCES users(id)
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
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute(
        """
        SELECT
            id,
            owner_user_id,
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
        WHERE id = ? AND owner_user_id = ?
        """,
        (agent_id, owner_user_id)
    )

    row = cur.fetchone()
    conn.close()

    if not row:
        return None

    tools_raw = row[9] or "{}"
    try:
        tools = json.loads(tools_raw)
    except Exception:
        tools = {}

    return {
        "id": row[0],
        "owner_user_id": row[1],
        "name": row[2],
        "business_name": row[3],
        "phone_number": row[4],
        "system_prompt": row[5],
        "voice": row[6],
        "provider": row[7],
        "first_message": row[8],
        "tools": tools,
        "created_at": row[10],
        "updated_at": row[11],
    }

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
