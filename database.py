import os
import psycopg2

def log_decision(canonical_id, trust_score, decision, primary_issue, config_version):
    print("--- ATTEMPTING DATABASE SAVE ---")
    
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        print("❌ ERROR: DATABASE_URL is missing in Render Environment Variables!")
        return

    try:
        # Connect to Neon PostgreSQL
        conn = psycopg2.connect(db_url, sslmode='require')
        cur = conn.cursor()
        
        # Insert the record
        cur.execute(
            "INSERT INTO decisions (canonical_id, trust_score, decision, primary_issue, config_version) VALUES (%s, %s, %s, %s, %s)",
            (canonical_id, trust_score, decision, primary_issue, config_version)
        )
        
        # Commit the transaction
        conn.commit()
        print(f"✅ SUCCESS: Saved {canonical_id} to Neon!")
        
        cur.close()
        conn.close()
        
    except Exception as e:
        print(f"❌ DATABASE ERROR: {str(e)}")
