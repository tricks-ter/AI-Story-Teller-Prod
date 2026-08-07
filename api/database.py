import os
import psycopg2
from psycopg2 import extras
import json
from dotenv import load_dotenv
import logging

load_dotenv()
logger = logging.getLogger(__name__)

class Database:
    def __init__(self):
        self.database_url = os.getenv("DATABASE_URL")
        if self.database_url and "sslmode" not in self.database_url:
            separator = "&" if "?" in self.database_url else "?"
            self.database_url += f"{separator}sslmode=require"

    def get_connection(self):
        if not self.database_url: return None
        try: return psycopg2.connect(self.database_url, connect_timeout=10)
        except Exception as e:
            logger.error(f"DB Connection error: {e}")
            return None

    def execute_query(self, query, params=None, fetch="all", commit=False):
        conn = self.get_connection()
        if not conn: return None
        try:
            with conn.cursor(cursor_factory=extras.RealDictCursor) as cur:
                cur.execute(query, params or ())
                if fetch == "all": res = cur.fetchall()
                elif fetch == "one": res = cur.fetchone()
                else: res = None
                if commit: conn.commit()
                return res
        except Exception as e:
            try: conn.rollback()
            except Exception: pass
            logger.error(f"DB Query error: {e}")
            return None
        finally: conn.close()

    def init_tables(self):
        if not self.database_url: return
        queries = [
            "CREATE TABLE IF NOT EXISTS chat_sessions (id VARCHAR(36) PRIMARY KEY, title VARCHAR(255) NOT NULL, created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP, updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP)",
            "CREATE TABLE IF NOT EXISTS chat_messages (id SERIAL PRIMARY KEY, session_id VARCHAR(36) REFERENCES chat_sessions(id) ON DELETE CASCADE, role VARCHAR(20) NOT NULL, content TEXT NOT NULL, created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP, metadata JSONB)"
        ]
        for q in queries:
            self.execute_query(q, fetch="none", commit=True)

    def ensure_session(self, session_id, title="New Chat"):
        if not self.database_url: return
        self.execute_query(
            "INSERT INTO chat_sessions (id, title) VALUES (%s, %s) ON CONFLICT (id) DO NOTHING",
            (session_id, title), fetch="none", commit=True)

    def add_message(self, session_id, role, content, metadata=None):
        if not self.database_url: return
        self.execute_query(
            "INSERT INTO chat_messages (session_id, role, content, metadata) VALUES (%s, %s, %s, %s)",
            (session_id, role, content, json.dumps(metadata) if metadata else None),
            fetch="none", commit=True)

db = Database()
