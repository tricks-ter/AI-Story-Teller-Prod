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
            """CREATE TABLE IF NOT EXISTS users (
                id VARCHAR(36) PRIMARY KEY,
                username VARCHAR(80) UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role VARCHAR(20) DEFAULT 'user',
                metadata JSONB DEFAULT '{}'::jsonb,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP)""",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS metadata JSONB DEFAULT '{}'::jsonb",
            """CREATE TABLE IF NOT EXISTS auth_tokens (
                token VARCHAR(128) PRIMARY KEY,
                user_id VARCHAR(36) REFERENCES users(id) ON DELETE CASCADE,
                expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP)""",
            """CREATE TABLE IF NOT EXISTS chat_sessions (
                id VARCHAR(36) PRIMARY KEY,
                title VARCHAR(255) NOT NULL,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP)""",
            "ALTER TABLE chat_sessions ADD COLUMN IF NOT EXISTS user_id VARCHAR(36)",
            """CREATE TABLE IF NOT EXISTS chat_messages (
                id SERIAL PRIMARY KEY,
                session_id VARCHAR(36) REFERENCES chat_sessions(id) ON DELETE CASCADE,
                role VARCHAR(20) NOT NULL,
                content TEXT NOT NULL,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                metadata JSONB)""",
            "ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS user_id VARCHAR(36)",
            """CREATE TABLE IF NOT EXISTS stories (
                id VARCHAR(36) PRIMARY KEY,
                title VARCHAR(255) NOT NULL,
                genre VARCHAR(100),
                premise TEXT,
                current_day INT DEFAULT 1,
                time_of_day VARCHAR(50) DEFAULT 'Morning',
                creator_id VARCHAR(36),
                is_premium BOOLEAN DEFAULT FALSE,
                energy_cost INT DEFAULT 0,
                metadata JSONB DEFAULT '{}'::jsonb,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP)""",
            """CREATE TABLE IF NOT EXISTS story_characters (
                id VARCHAR(36) PRIMARY KEY,
                story_id VARCHAR(36) REFERENCES stories(id) ON DELETE CASCADE,
                name VARCHAR(255) NOT NULL,
                role VARCHAR(100),
                background TEXT,
                is_player BOOLEAN DEFAULT TRUE,
                metadata JSONB DEFAULT '{}'::jsonb,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP)""",
            """CREATE TABLE IF NOT EXISTS story_messages (
                id SERIAL PRIMARY KEY,
                story_id VARCHAR(36) REFERENCES stories(id) ON DELETE CASCADE,
                role VARCHAR(20) NOT NULL,
                content TEXT NOT NULL,
                message_type VARCHAR(50) DEFAULT 'narration',
                metadata JSONB DEFAULT '{}'::jsonb,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP)"""
        ]
        for q in queries:
            self.execute_query(q, fetch="none", commit=True)

    # ── Auth / Users ──
    def create_user(self, user_id, username, password_hash, metadata=None):
        self.execute_query(
            "INSERT INTO users (id, username, password_hash, metadata) VALUES (%s, %s, %s, %s)",
            (user_id, username, password_hash, json.dumps(metadata) if metadata else "{}"),
            fetch="none", commit=True)

    def get_user_by_username(self, username):
        return self.execute_query(
            "SELECT id, username, password_hash, role, metadata FROM users WHERE username = %s",
            (username,), fetch="one")

    def get_user_by_id(self, user_id):
        return self.execute_query(
            "SELECT id, username, role, metadata FROM users WHERE id = %s",
            (user_id,), fetch="one")

    def update_user_metadata(self, user_id, metadata):
        self.execute_query(
            "UPDATE users SET metadata = %s WHERE id = %s",
            (json.dumps(metadata) if metadata is not None else "{}", user_id),
            fetch="none", commit=True)

    # ── Quick Chat ──
    def ensure_session(self, session_id, title="New Chat", user_id=None):
        if not self.database_url: return
        self.execute_query(
            "INSERT INTO chat_sessions (id, title, user_id) VALUES (%s, %s, %s) "
            "ON CONFLICT (id) DO UPDATE SET user_id = COALESCE(EXCLUDED.user_id, chat_sessions.user_id)",
            (session_id, title, user_id), fetch="none", commit=True)

    def add_message(self, session_id, role, content, metadata=None, user_id=None):
        if not self.database_url: return
        self.execute_query(
            "INSERT INTO chat_messages (session_id, role, content, metadata, user_id) VALUES (%s, %s, %s, %s, %s)",
            (session_id, role, content, json.dumps(metadata) if metadata else None, user_id),
            fetch="none", commit=True)

    # ── Stories ──
    def create_story(self, story_id, title, genre, premise, metadata=None, creator_id=None):
        if not self.database_url: return
        self.execute_query(
            "INSERT INTO stories (id, title, genre, premise, metadata, creator_id) VALUES (%s, %s, %s, %s, %s, %s)",
            (story_id, title, genre, premise, json.dumps(metadata) if metadata else "{}", creator_id),
            fetch="none", commit=True)

    def add_story_character(self, char_id, story_id, name, role, background, metadata=None):
        if not self.database_url: return
        self.execute_query(
            "INSERT INTO story_characters (id, story_id, name, role, background, metadata) VALUES (%s, %s, %s, %s, %s, %s)",
            (char_id, story_id, name, role, background, json.dumps(metadata) if metadata else "{}"),
            fetch="none", commit=True)

    def add_story_message(self, story_id, role, content, msg_type="narration", metadata=None):
        if not self.database_url: return
        self.execute_query(
            "INSERT INTO story_messages (story_id, role, content, message_type, metadata) VALUES (%s, %s, %s, %s, %s)",
            (story_id, role, content, msg_type, json.dumps(metadata) if metadata else "{}"),
            fetch="none", commit=True)

    def list_stories_for_user(self, user_id):
        if not self.database_url: return []
        return self.execute_query(
            "SELECT id, title, genre, premise, current_day, time_of_day, is_premium, updated_at "
            "FROM stories WHERE creator_id = %s ORDER BY updated_at DESC",
            (user_id,), fetch="all") or []

db = Database()

try:
    db.init_tables()
except Exception as e:
    logger.error(f"DB init warning: {e}")
