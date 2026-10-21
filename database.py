import os
import psycopg2

def log_decision(canonical_id, trust_score, decision, primary_issue, config_version):
    print("--- ATTEMPTING DATABASE SAVE ---")
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        print("❌ ERROR: DATABASE_URL is missing!")
        return

    try:
        conn = psycopg2.connect(db_url, sslmode='require')
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO decisions (canonical_id, trust_score, decision, primary_issue, config_version) VALUES (%s, %s, %s, %s, %s)",
            (canonical_id, trust_score, decision, primary_issue, config_version)
        )
        conn.commit()
        cur.close()
        conn.close()
        print(f"✅ SUCCESS: Saved {canonical_id} to Neon!")
    except Exception as e:
        print(f"❌ DATABASE ERROR: {str(e)}")

# --- THE FIX: Dummy class to satisfy trust_engine.py ---
class AuditDatabase:
    def __init__(self, *args, **kwargs):
        pass # Do nothing
        
    def log_decision(self, *args, **kwargs):
        pass # Do nothing (app.py handles the real save now)
