import sqlite3
import json
from datetime import datetime

class AuditDatabase:
    def __init__(self, db_path="audit_log.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """Create the table if it doesn't exist."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS decisions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT,
                    canonical_id TEXT,
                    trust_score REAL,
                    decision TEXT,
                    primary_issue TEXT,
                    dimensions TEXT
                )
            ''')
            conn.commit()

    def log_decision(self, result_dict):
        """Save a single decision to the database."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO decisions (timestamp, canonical_id, trust_score, decision, primary_issue, dimensions)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                datetime.now().isoformat(),
                result_dict.get('canonical_id'),
                result_dict.get('trust_score'),
                result_dict.get('decision'),
                result_dict.get('primary_issue'),
                json.dumps(result_dict.get('dimensions'))
            ))
            conn.commit()

    def get_recent_decisions(self, limit=50):
        """Fetch the most recent decisions for the dashboard."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM decisions ORDER BY id DESC LIMIT ?', (limit,))
            return [dict(row) for row in cursor.fetchall()]
