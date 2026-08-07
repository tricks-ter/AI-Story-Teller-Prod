import os
import threading
import psycopg2
from psycopg2 import extras
import json
from dotenv import load_dotenv
import logging

load_dotenv()
logger = logging.getLogger(__name__)

LEGACY_USER_ID = "legacy-system"

class Database:
    def __init__(self):
        self.database_url = os.getenv("DATABASE_URL")
        if self.database_url and "sslmode" not in self.database_url:
            separator = "&" if "?" in self.database_url else "?"
            self.database_url += f"{separator}sslmode=require"
        self._conn = None
        self._lock = threading.RLock()

    def _get_conn(self):
        if not self.database_url: return None
        if self._conn is not None and not self._conn.closed:
            return self._conn
        try:
            self._conn = psycopg2.connect(self.database_url, connect_timeout=5)
            return self._conn
        except Exception as e:
            logger.error(f"DB Connection error: {e}")
            self._conn = None
            return None

    def _reset_conn(self):
        try:
            if self._conn is not None: self._conn.close()
        except Exception: pass
        self._conn = None

    def _with_conn(self, fn, commit=False):
        if not self.database_url: return None
        with self._lock:
            last_err = None
            for attempt in range(2):
                conn = self._get_conn()
                if conn is None: return None
                try:
                    with conn.cursor(cursor_factory=extras.RealDictCursor) as cur:
                        result = fn(cur)
                    if commit: conn.commit()
                    return result
                except (psycopg2.OperationalError, psycopg2.InterfaceError) as e:
                    last_err = e
                    self._reset_conn()
                except Exception as e:
                    last_err = e
                    try: conn.rollback()
                    except Exception: pass
                    break
            logger.error(f"DB Query error: {last_err}")
            return None

    def execute_query(self, query, params=None, fetch="all", commit=False):
        def fn(cur):
            cur.execute(query, params or ())
            if fetch == "all": return cur.fetchall()
            if fetch == "one": return cur.fetchone()
            return None
        return self._with_conn(fn, commit=commit)

    def init_tables(self):
        if not self.database_url: return

        # 1) Reserved system account for pre-auth legacy rows (can never log in)
        self.execute_query(
            "INSERT INTO users (id, username, password_hash, role, metadata) "
            "VALUES ('legacy-system', 'legacy-system', '!', 'user', '{}'::jsonb) "
            "ON CONFLICT (id) DO NOTHING", fetch="none", commit=True)

        # 2) Fresh installs: full NOT NULL schema
        ddl = """
        CREATE TABLE IF NOT EXISTS users (
            id VARCHAR(36) PRIMARY KEY,
            username VARCHAR(80) UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role VARCHAR(20) NOT NULL DEFAULT 'user',
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS auth_tokens (
            token VARCHAR(128) PRIMARY KEY,
            user_id VARCHAR(36) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS chat_sessions (
            id VARCHAR(36) PRIMARY KEY,
            title VARCHAR(255) NOT NULL,
            user_id VARCHAR(36) NOT NULL DEFAULT 'legacy-system',
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS chat_messages (
            id SERIAL PRIMARY KEY,
            session_id VARCHAR(36) NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
            role VARCHAR(20) NOT NULL,
            content TEXT NOT NULL,
            user_id VARCHAR(36) NOT NULL DEFAULT 'legacy-system',
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS stories (
            id VARCHAR(36) PRIMARY KEY,
            title VARCHAR(255) NOT NULL,
            genre VARCHAR(100) NOT NULL DEFAULT 'Unknown',
            premise TEXT NOT NULL DEFAULT '',
            current_day INT NOT NULL DEFAULT 1,
            time_of_day VARCHAR(50) NOT NULL DEFAULT 'Morning',
            creator_id VARCHAR(36) NOT NULL DEFAULT 'legacy-system',
            is_premium BOOLEAN NOT NULL DEFAULT FALSE,
            energy_cost INT NOT NULL DEFAULT 0,
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS story_characters (
            id VARCHAR(36) PRIMARY KEY,
            story_id VARCHAR(36) NOT NULL REFERENCES stories(id) ON DELETE CASCADE,
            name VARCHAR(255) NOT NULL,
            role VARCHAR(100) NOT NULL DEFAULT 'Character',
            background TEXT NOT NULL DEFAULT '',
            is_player BOOLEAN NOT NULL DEFAULT TRUE,
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS story_messages (
            id SERIAL PRIMARY KEY,
            story_id VARCHAR(36) NOT NULL REFERENCES stories(id) ON DELETE CASCADE,
            role VARCHAR(20) NOT NULL,
            content TEXT NOT NULL,
            message_type VARCHAR(50) NOT NULL DEFAULT 'narration',
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP);
        """
        self.execute_query(ddl, fetch="none", commit=True)

        # 3) Existing installs: backfill NULLs, then lock columns (per-table isolation)
        migrations = [
            """UPDATE users SET metadata = '{}'::jsonb WHERE metadata IS NULL;
               UPDATE users SET role = 'user' WHERE role IS NULL;
               ALTER TABLE users ALTER COLUMN metadata SET DEFAULT '{}'::jsonb;
               ALTER TABLE users ALTER COLUMN metadata SET NOT NULL;
               ALTER TABLE users ALTER COLUMN role SET DEFAULT 'user';
               ALTER TABLE users ALTER COLUMN role SET NOT NULL;""",
            """UPDATE chat_sessions SET user_id = 'legacy-system' WHERE user_id IS NULL;
               ALTER TABLE chat_sessions ALTER COLUMN user_id SET DEFAULT 'legacy-system';
               ALTER TABLE chat_sessions ALTER COLUMN user_id SET NOT NULL;""",
            """UPDATE chat_messages SET user_id = 'legacy-system' WHERE user_id IS NULL;
               UPDATE chat_messages SET metadata = '{}'::jsonb WHERE metadata IS NULL;
               ALTER TABLE chat_messages ALTER COLUMN user_id SET DEFAULT 'legacy-system';
               ALTER TABLE chat_messages ALTER COLUMN user_id SET NOT NULL;
               ALTER TABLE chat_messages ALTER COLUMN metadata SET DEFAULT '{}'::jsonb;
               ALTER TABLE chat_messages ALTER COLUMN metadata SET NOT NULL;""",
            """UPDATE stories SET creator_id = 'legacy-system' WHERE creator_id IS NULL;
               UPDATE stories SET genre = 'Unknown' WHERE genre IS NULL;
               UPDATE stories SET premise = '' WHERE premise IS NULL;
               UPDATE stories SET current_day = 1 WHERE current_day IS NULL;
               UPDATE stories SET time_of_day = 'Morning' WHERE time_of_day IS NULL;
               UPDATE stories SET is_premium = FALSE WHERE is_premium IS NULL;
               UPDATE stories SET energy_cost = 0 WHERE energy_cost IS NULL;
               UPDATE stories SET metadata = '{}'::jsonb WHERE metadata IS NULL;
               ALTER TABLE stories ALTER COLUMN creator_id SET DEFAULT 'legacy-system';
               ALTER TABLE stories ALTER COLUMN creator_id SET NOT NULL;
               ALTER TABLE stories ALTER COLUMN genre SET DEFAULT 'Unknown';
               ALTER TABLE stories ALTER COLUMN genre SET NOT NULL;
               ALTER TABLE stories ALTER COLUMN premise SET DEFAULT '';
               ALTER TABLE stories ALTER COLUMN premise SET NOT NULL;
               ALTER TABLE stories ALTER COLUMN current_day SET DEFAULT 1;
               ALTER TABLE stories ALTER COLUMN current_day SET NOT NULL;
               ALTER TABLE stories ALTER COLUMN time_of_day SET DEFAULT 'Morning';
               ALTER TABLE stories ALTER COLUMN time_of_day SET NOT NULL;
               ALTER TABLE stories ALTER COLUMN is_premium SET DEFAULT FALSE;
               ALTER TABLE stories ALTER COLUMN is_premium SET NOT NULL;
               ALTER TABLE stories ALTER COLUMN energy_cost SET DEFAULT 0;
               ALTER TABLE stories ALTER COLUMN energy_cost SET NOT NULL;
               ALTER TABLE stories ALTER COLUMN metadata SET DEFAULT '{}'::jsonb;
               ALTER TABLE stories ALTER COLUMN metadata SET NOT NULL;""",
            """UPDATE story_characters SET role = 'Character' WHERE role IS NULL;
               UPDATE story_characters SET background = '' WHERE background IS NULL;
               UPDATE story_characters SET is_player = TRUE WHERE is_player IS NULL;
               UPDATE story_characters SET metadata = '{}'::jsonb WHERE metadata IS NULL;
               ALTER TABLE story_characters ALTER COLUMN role SET DEFAULT 'Character';
               ALTER TABLE story_characters ALTER COLUMN role SET NOT NULL;
               ALTER TABLE story_characters ALTER COLUMN background SET DEFAULT '';
               ALTER TABLE story_characters ALTER COLUMN background SET NOT NULL;
               ALTER TABLE story_characters ALTER COLUMN is_player SET DEFAULT TRUE;
               ALTER TABLE story_characters ALTER COLUMN is_player SET NOT NULL;
               ALTER TABLE story_characters ALTER COLUMN metadata SET DEFAULT '{}'::jsonb;
               ALTER TABLE story_characters ALTER COLUMN metadata SET NOT NULL;""",
            """UPDATE story_messages SET message_type = 'narration' WHERE message_type IS NULL;
               UPDATE story_messages SET metadata = '{}'::jsonb WHERE metadata IS NULL;
               ALTER TABLE story_messages ALTER COLUMN message_type SET DEFAULT 'narration';
               ALTER TABLE story_messages ALTER COLUMN message_type SET NOT NULL;
               ALTER TABLE story_messages ALTER COLUMN metadata SET DEFAULT '{}'::jsonb;
               ALTER TABLE story_messages ALTER COLUMN metadata SET NOT NULL;"""
        ]
        for m in migrations:
            self.execute_query(m, fetch="none", commit=True)

    # ── Auth / Users ──
    def create_user_with_token(self, user_id, username, password_hash, token, expires_at, metadata=None):
        def fn(cur):
            cur.execute(
                "INSERT INTO users (id, username, password_hash, metadata) VALUES (%s, %s, %s, %s)",
                (user_id, username, password_hash, json.dumps(metadata) if metadata else "{}"))
            cur.execute(
                "INSERT INTO auth_tokens (token, user_id, expires_at) VALUES (%s, %s, %s)",
                (token, user_id, expires_at))
            return True
        return self._with_conn(fn, commit=True) is True

    def add_auth_token(self, token, user_id, expires_at):
        def fn(cur):
            cur.execute(
                "INSERT INTO auth_tokens (token, user_id, expires_at) VALUES (%s, %s, %s)",
                (token, user_id, expires_at))
            return True
        return self._with_conn(fn, commit=True) is True

    def create_user(self, user_id, username, password_hash, metadata=None):
        return self.execute_query(
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
        uid = user_id or LEGACY_USER_ID
        self.execute_query(
            "INSERT INTO chat_sessions (id, title, user_id) VALUES (%s, %s, %s) "
            "ON CONFLICT (id) DO UPDATE SET user_id = COALESCE(EXCLUDED.user_id, chat_sessions.user_id)",
            (session_id, title, uid), fetch="none", commit=True)

    def add_message(self, session_id, role, content, metadata=None, user_id=None):
        if not self.database_url: return
        uid = user_id or LEGACY_USER_ID
        self.execute_query(
            "INSERT INTO chat_messages (session_id, role, content, metadata, user_id) VALUES (%s, %s, %s, %s, %s)",
            (session_id, role, content, json.dumps(metadata) if metadata else "{}", uid),
            fetch="none", commit=True)

    # ── Stories ──
    def create_story(self, story_id, title, genre, premise, metadata=None, creator_id=None):
        if not self.database_url: return
        cid = creator_id or LEGACY_USER_ID
        self.execute_query(
            "INSERT INTO stories (id, title, genre, premise, metadata, creator_id) VALUES (%s, %s, %s, %s, %s, %s)",
            (story_id, title, genre, premise, json.dumps(metadata) if metadata else "{}", cid),
            fetch="none", commit=True)

    def add_story_character(self, char_id, story_id, name, role, background, metadata=None):
        if not self.database_url: return
        self.execute_query(
            "INSERT INTO story_characters (id, story_id, name, role, background, metadata) VALUES (%s, %s, %s, %s, %s, %s)",
            (char_id, story_id, name, role or "Character", background or "", json.dumps(metadata) if metadata else "{}"),
            fetch="none", commit=True)

    def add_story_message(self, story_id, role, content, msg_type="narration", metadata=None):
        if not self.database_url: return
        self.execute_query(
            "INSERT INTO story_messages (story_id, role, content, message_type, metadata) VALUES (%s, %s, %s, %s, %s)",
            (story_id, role, content, msg_type or "narration", json.dumps(metadata) if metadata else "{}"),
            fetch="none", commit=True)

    def list_stories_for_user(self, user_id):
        if not self.database_url: return []
        return self.execute_query(
            "SELECT s.id, s.title, s.genre, s.premise, s.current_day, s.time_of_day, s.is_premium, s.updated_at, "
            "(SELECT sc.name FROM story_characters sc WHERE sc.story_id = s.id AND sc.is_player = TRUE ORDER BY sc.created_at ASC LIMIT 1) AS character_name, "
            "(SELECT sc.role FROM story_characters sc WHERE sc.story_id = s.id AND sc.is_player = TRUE ORDER BY sc.created_at ASC LIMIT 1) AS character_role "
            "FROM stories s WHERE s.creator_id = %s ORDER BY s.updated_at DESC",
            (user_id,), fetch="all") or []

    def get_story(self, story_id):
        return self.execute_query(
            "SELECT * FROM stories WHERE id = %s", (story_id,), fetch="one")

    def get_story_characters(self, story_id):
        return self.execute_query(
            "SELECT id, name, role, background, is_player, metadata, created_at "
            "FROM story_characters WHERE story_id = %s ORDER BY is_player DESC, created_at ASC",
            (story_id,), fetch="all") or []

    def get_story_messages(self, story_id, limit=50):
        return self.execute_query(
            "SELECT id, role, content, message_type, created_at "
            "FROM story_messages WHERE story_id = %s ORDER BY id ASC LIMIT %s",
            (story_id, int(limit)), fetch="all") or []

db = Database()

try:
    db.init_tables()
except Exception as e:
    logger.error(f"DB init warning: {e}")
