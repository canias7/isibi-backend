"""
Database Migration: Add Voice Provider Support

Run this to add voice provider columns to the agents table
"""

from db import get_conn

def migrate_add_voice_providers():
    """
    Add voice_provider and elevenlabs_voice_id columns to agents table
    """
    conn = get_conn()
    cur = conn.cursor()
    
    try:
        # Add voice_provider column (default to 'openai')
        cur.execute("""
            ALTER TABLE agents 
            ADD COLUMN IF NOT EXISTS voice_provider VARCHAR(50) DEFAULT 'openai'
        """)
        
        # Add elevenlabs_voice_id column for ElevenLabs voices
        cur.execute("""
            ALTER TABLE agents 
            ADD COLUMN IF NOT EXISTS elevenlabs_voice_id VARCHAR(100)
        """)
        
        # Add voice_settings JSON column for advanced settings
        cur.execute("""
            ALTER TABLE agents 
            ADD COLUMN IF NOT EXISTS voice_settings JSONB DEFAULT '{}'::jsonb
        """)
        
        conn.commit()
        print("✅ Migration successful: Added voice provider columns")
        
    except Exception as e:
        conn.rollback()
        print(f"❌ Migration failed: {e}")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    migrate_add_voice_providers()
