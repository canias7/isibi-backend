import sqlite3

DB_PATH = "app.db"


def init_db():
    conn = sqlite3.connect(DB_PATH)
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

