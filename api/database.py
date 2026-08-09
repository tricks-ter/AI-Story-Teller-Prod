import os
import threading
import json
import uuid
import logging
from datetime import datetime, timezone
import psycopg2
from psycopg2 import extras
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

LEGACY_USER_ID = "legacy-system"

def _merge_telemetry(existing, telemetry, telemetry_key="client_telemetry"):
    base = (existing or {}) if isinstance(existing, dict) else {}
    out = dict(base)
    if telemetry is not None:
        out[telemetry_key] = telemetry
    return out

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
        # Runtime is migration-free. Schema is applied at deploy time by api/migrate.py.
        if not self.database_url:
            logger.warning("DATABASE_URL not set — running without DB.")
            return
        row = self.execute_query("SELECT 1", fetch="one")
        if row is None:
            logger.warning("DB not reachable at boot.")

    # ── Auth / Users ──
    def create_user_with_token(self, user_id, username, password_hash, token, expires_at, metadata=None, telemetry=None):
        merged = _merge_telemetry(metadata, telemetry, telemetry_key="signup_telemetry")
        def fn(cur):
            cur.execute(
                "INSERT INTO users (id, username, password_hash, role, metadata, created_at) "
                "VALUES (%s, %s, %s, %s, %s, CURRENT_TIMESTAMP)",
                (user_id, username, password_hash, "user", json.dumps(merged)))
            cur.execute(
                "INSERT INTO auth_tokens (token, user_id, expires_at, created_at) "
                "VALUES (%s, %s, %s, CURRENT_TIMESTAMP)",
                (token, user_id, expires_at))
            return True
        return self._with_conn(fn, commit=True) is True

    def add_auth_token(self, token, user_id, expires_at):
        def fn(cur):
            cur.execute(
                "INSERT INTO auth_tokens (token, user_id, expires_at, created_at) "
                "VALUES (%s, %s, %s, CURRENT_TIMESTAMP)",
                (token, user_id, expires_at))
            return True
        return self._with_conn(fn, commit=True) is True

    def touch_user_login(self, user_id, telemetry=None):
        def fn(cur):
            cur.execute("SELECT metadata FROM users WHERE id = %s", (user_id,))
            row = cur.fetchone()
            meta = (row["metadata"] if row and isinstance(row["metadata"], dict) else {}) or {}
            new_meta = {
                "preferences": meta.get("preferences", {}),
                "energy_credits": meta.get("energy_credits", 0),
                "login_count": int(meta.get("login_count", 0)) + 1,
                "last_login_at": datetime.now(timezone.utc).isoformat(),
                "created_via": meta.get("created_via", "signup"),
                "signup_telemetry": meta.get("signup_telemetry"),
            }
            if telemetry is not None:
                new_meta["last_login_telemetry"] = telemetry
            cur.execute("UPDATE users SET metadata = %s WHERE id = %s",
                        (json.dumps(new_meta), user_id))
            return new_meta
        return self._with_conn(fn, commit=True) or {}

    def create_user(self, user_id, username, password_hash, metadata=None, telemetry=None):
        merged = _merge_telemetry(metadata, telemetry, telemetry_key="signup_telemetry")
        return self.execute_query(
            "INSERT INTO users (id, username, password_hash, role, metadata, created_at) "
            "VALUES (%s, %s, %s, %s, %s, CURRENT_TIMESTAMP)",
            (user_id, username, password_hash, "user", json.dumps(merged)),
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
            "INSERT INTO chat_sessions (id, title, user_id, created_at, updated_at) "
            "VALUES (%s, %s, %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP) "
            "ON CONFLICT (id) DO UPDATE SET user_id = COALESCE(EXCLUDED.user_id, chat_sessions.user_id), "
            "updated_at = CURRENT_TIMESTAMP",
            (session_id, title, uid), fetch="none", commit=True)

    def add_message(self, session_id, role, content, metadata=None, user_id=None, telemetry=None):
        if not self.database_url: return
        uid = user_id or LEGACY_USER_ID
        merged = _merge_telemetry(metadata, telemetry, telemetry_key="client_telemetry")
        self.execute_query(
            "INSERT INTO chat_messages (session_id, role, content, user_id, metadata, created_at) "
            "VALUES (%s, %s, %s, %s, %s, CURRENT_TIMESTAMP)",
            (session_id, role, content, uid, json.dumps(merged)),
            fetch="none", commit=True)

    # ── Stories (templates) ──
    def create_story(self, story_id, title, genre, premise, metadata=None, creator_id=None, telemetry=None):
        if not self.database_url: return
        cid = creator_id or LEGACY_USER_ID
        merged = _merge_telemetry(metadata, telemetry, telemetry_key="created_telemetry")
        self.execute_query(
            "INSERT INTO stories (id, title, genre, premise, current_day, time_of_day, creator_id, "
            "is_premium, energy_cost, metadata, created_at, updated_at) "
            "VALUES (%s, %s, %s, %s, 1, 'Morning', %s, FALSE, 0, %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
            (story_id, title, genre, premise, cid, json.dumps(merged)),
            fetch="none", commit=True)

    def add_story_character(self, char_id, story_id, name, role, background, metadata=None, telemetry=None):
        if not self.database_url: return
        merged = _merge_telemetry(metadata, telemetry, telemetry_key="created_telemetry")
        self.execute_query(
            "INSERT INTO story_characters (id, story_id, name, role, background, is_player, metadata, created_at) "
            "VALUES (%s, %s, %s, %s, %s, TRUE, %s, CURRENT_TIMESTAMP)",
            (char_id, story_id, name, role or "Character", background or "", json.dumps(merged)),
            fetch="none", commit=True)

    def add_story_message(self, story_id, role, content, msg_type="narration", metadata=None, telemetry=None):
        if not self.database_url: return
        merged = _merge_telemetry(metadata, telemetry, telemetry_key="client_telemetry")
        self.execute_query(
            "INSERT INTO story_messages (story_id, role, content, message_type, metadata, created_at) "
            "VALUES (%s, %s, %s, %s, %s, CURRENT_TIMESTAMP)",
            (story_id, role, content, msg_type or "narration", json.dumps(merged)),
            fetch="none", commit=True)

    def list_stories_for_user(self, user_id):
        if not self.database_url: return []
        return self.execute_query(
            "SELECT s.id, s.title, s.genre, s.premise, s.current_day, s.time_of_day, s.is_premium, s.updated_at, "
            "(SELECT sc.name FROM story_characters sc WHERE sc.story_id = s.id AND sc.is_player = TRUE ORDER BY sc.created_at ASC LIMIT 1) AS character_name, "
            "(SELECT sc.role FROM story_characters sc WHERE sc.story_id = s.id AND sc.is_player = TRUE ORDER BY sc.created_at ASC LIMIT 1) AS character_role "
            "FROM stories s WHERE s.creator_id = %s ORDER BY s.updated_at DESC",
            (user_id,), fetch="all") or []

    def list_all_stories(self, user_id):
        if not self.database_url: return []
        return self.execute_query(
            "SELECT s.id, s.title, s.genre, s.premise, s.is_premium, s.updated_at, u.username AS creator_name, "
            "(SELECT sc.name FROM story_characters sc WHERE sc.story_id = s.id AND sc.is_player = TRUE ORDER BY sc.created_at ASC LIMIT 1) AS character_name, "
            "(SELECT sc.role FROM story_characters sc WHERE sc.story_id = s.id AND sc.is_player = TRUE ORDER BY sc.created_at ASC LIMIT 1) AS character_role, "
            "(SELECT COUNT(*) FROM playthroughs p WHERE p.story_id = s.id AND p.user_id = %s) AS played_count "
            "FROM stories s LEFT JOIN users u ON u.id = s.creator_id "
            "ORDER BY s.updated_at DESC LIMIT 100",
            (user_id,), fetch="all") or []

    def get_story(self, story_id):
        return self.execute_query(
            "SELECT * FROM stories WHERE id = %s", (story_id,), fetch="one")

    def get_story_characters(self, story_id):
        return self.execute_query(
            "SELECT id, name, role, background, is_player, metadata, created_at "
            "FROM story_characters WHERE story_id = %s ORDER BY is_player DESC, created_at ASC",
            (story_id,), fetch="all") or []

    # SECURITY FIX: base_only=True returns ONLY the author's template/intro rows
    # (playthrough_id='legacy'), never any player's private playthrough turns.
    def get_story_messages(self, story_id, limit=50, base_only=True):
        query = ("SELECT id, role, content, message_type, created_at "
                 "FROM story_messages WHERE story_id = %s")
        params = [story_id]
        if base_only:
            query += " AND playthrough_id = 'legacy'"
        query += " ORDER BY id ASC LIMIT %s"
        params.append(int(limit))
        return self.execute_query(query, tuple(params), fetch="all") or []

    def get_story_notes(self, story_id, active_only=True):
        query = "SELECT content, priority FROM story_notes WHERE story_id = %s"
        if active_only:
            query += " AND is_active = TRUE"
        query += " ORDER BY priority DESC, id ASC LIMIT 10"
        return self.execute_query(query, (story_id,), fetch="all") or []

    def add_story_note(self, story_id, content, priority=5, is_active=True):
        self.execute_query(
            "INSERT INTO story_notes (story_id, content, priority, is_active, created_at) "
            "VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP)",
            (story_id, content, int(priority), bool(is_active)),
            fetch="none", commit=True)

    # ── Playthroughs ──
    def get_active_playthrough(self, story_id, user_id):
        return self.execute_query(
            "SELECT * FROM playthroughs WHERE story_id = %s AND user_id = %s AND status = 'active' "
            "ORDER BY updated_at DESC LIMIT 1",
            (story_id, user_id), fetch="one")

    def get_playthrough(self, playthrough_id):
        return self.execute_query(
            "SELECT * FROM playthroughs WHERE id = %s", (playthrough_id,), fetch="one")

    def create_playthrough(self, story_id, user_id):
        pid = str(uuid.uuid4())
        def fn(cur):
            cur.execute(
                "INSERT INTO playthroughs (id, story_id, user_id, current_day, time_of_day, status, metadata, created_at, updated_at) "
                "VALUES (%s, %s, %s, 1, 'Morning', 'active', '{}', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
                (pid, story_id, user_id))
            cur.execute(
                "INSERT INTO playthrough_characters (id, playthrough_id, character_name, role, background, is_player, metadata, created_at) "
                "SELECT substr(md5(random()::text || sc.id), 1, 36), %s, sc.name, sc.role, sc.background, sc.is_player, sc.metadata, CURRENT_TIMESTAMP "
                "FROM story_characters sc WHERE sc.story_id = %s",
                (pid, story_id))
            # SECURITY/UX FIX: seed this playthrough with ONLY the author's base
            # intro rows (playthrough_id='legacy') — never other players' turns.
            cur.execute(
                "INSERT INTO story_messages (story_id, playthrough_id, role, content, message_type, metadata, created_at) "
                "SELECT %s, %s, role, content, message_type, metadata, CURRENT_TIMESTAMP "
                "FROM story_messages WHERE story_id = %s AND playthrough_id = 'legacy'",
                (story_id, pid, story_id))
            cur.execute("SELECT * FROM playthroughs WHERE id = %s", (pid,))
            return cur.fetchone()
        return self._with_conn(fn, commit=True)

    def get_playthrough_characters(self, playthrough_id):
        return self.execute_query(
            "SELECT id, character_name, role, background, is_player, metadata, created_at "
            "FROM playthrough_characters WHERE playthrough_id = %s ORDER BY is_player DESC, created_at ASC",
            (playthrough_id,), fetch="all") or []

    def get_playthrough_messages(self, playthrough_id, limit=50):
        return self.execute_query(
            "SELECT id, role, content, message_type, created_at "
            "FROM story_messages WHERE playthrough_id = %s ORDER BY id ASC LIMIT %s",
            (playthrough_id, int(limit)), fetch="all") or []

    def add_playthrough_message(self, story_id, playthrough_id, role, content, msg_type="narration", metadata=None, telemetry=None):
        if not self.database_url: return
        merged = _merge_telemetry(metadata, telemetry, telemetry_key="client_telemetry")
        self.execute_query(
            "INSERT INTO story_messages (story_id, playthrough_id, role, content, message_type, metadata, created_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)",
            (story_id, playthrough_id, role, content, msg_type or "narration", json.dumps(merged)),
            fetch="none", commit=True)

    def list_playthroughs_for_user(self, user_id):
        if not self.database_url: return []
        return self.execute_query(
            "SELECT p.id AS playthrough_id, p.story_id, p.current_day, p.time_of_day, p.status, p.updated_at, "
            "s.title, s.genre, s.premise, "
            "(SELECT pc.character_name FROM playthrough_characters pc WHERE pc.playthrough_id = p.id AND pc.is_player = TRUE LIMIT 1) AS character_name, "
            "(SELECT COUNT(*) FROM story_messages m WHERE m.playthrough_id = p.id) AS message_count "
            "FROM playthroughs p JOIN stories s ON s.id = p.story_id "
            "WHERE p.user_id = %s ORDER BY p.updated_at DESC LIMIT 100",
            (user_id,), fetch="all") or []

    # ── State updates (playthrough-scoped) ──
    def update_playthrough_time(self, playthrough_id, day, time_of_day):
        self.execute_query(
            "UPDATE playthroughs SET current_day = %s, time_of_day = %s, updated_at = CURRENT_TIMESTAMP WHERE id = %s",
            (int(day), str(time_of_day), playthrough_id),
            fetch="none", commit=True)

    def update_playthrough_location(self, playthrough_id, location):
        def fn(cur):
            cur.execute("SELECT metadata FROM playthroughs WHERE id = %s", (playthrough_id,))
            row = cur.fetchone()
            meta = (row["metadata"] if row and isinstance(row["metadata"], dict) else {}) or {}
            meta["current_location"] = location
            cur.execute("UPDATE playthroughs SET metadata = %s, updated_at = CURRENT_TIMESTAMP WHERE id = %s",
                        (json.dumps(meta), playthrough_id))
        self._with_conn(fn, commit=True)

    def upsert_playthrough_location(self, playthrough_id, location_name):
        def fn(cur):
            loc_id = str(uuid.uuid4())
            cur.execute(
                "SELECT id FROM locations WHERE playthrough_id = %s AND LOWER(name) = LOWER(%s)",
                (playthrough_id, location_name))
            row = cur.fetchone()
            if row:
                cur.execute("UPDATE locations SET is_discovered = TRUE, updated_at = CURRENT_TIMESTAMP WHERE id = %s", (row["id"],))
            else:
                cur.execute(
                    "INSERT INTO locations (id, playthrough_id, name, description, is_discovered, metadata, created_at, updated_at) "
                    "VALUES (%s, %s, %s, '', TRUE, '{}', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
                    (loc_id, playthrough_id, location_name))
            cur.execute("SELECT metadata FROM playthroughs WHERE id = %s", (playthrough_id,))
            pt_row = cur.fetchone()
            meta = (pt_row["metadata"] if pt_row and isinstance(pt_row["metadata"], dict) else {}) or {}
            meta["current_location"] = location_name
            cur.execute("UPDATE playthroughs SET metadata = %s, updated_at = CURRENT_TIMESTAMP WHERE id = %s",
                        (json.dumps(meta), playthrough_id))
        self._with_conn(fn, commit=True)

    def get_playthrough_locations(self, playthrough_id):
        return self.execute_query(
            "SELECT id, name, description, is_discovered, metadata, created_at, updated_at "
            "FROM locations WHERE playthrough_id = %s ORDER BY updated_at DESC",
            (playthrough_id,), fetch="all") or []

    def update_playthrough_character_stat(self, playthrough_id, character_name, stat_name, new_value, max_value=999):
        def fn(cur):
            cur.execute(
                "SELECT id, metadata FROM playthrough_characters WHERE playthrough_id = %s AND LOWER(character_name) = LOWER(%s) LIMIT 1",
                (playthrough_id, character_name))
            row = cur.fetchone()
            if not row: return False
            meta = (row["metadata"] if isinstance(row["metadata"], dict) else {}) or {}
            stats = meta.get("stats", {})
            stats[stat_name] = max(0, min(float(new_value), float(max_value)))
            meta["stats"] = stats
            cur.execute("UPDATE playthrough_characters SET metadata = %s WHERE id = %s",
                        (json.dumps(meta), row["id"]))
            return True
        return self._with_conn(fn, commit=True) is True

    # Legacy story-scoped state (kept for backward compat)
    def update_story_time(self, story_id, day, time_of_day):
        self.execute_query(
            "UPDATE stories SET current_day = %s, time_of_day = %s, updated_at = CURRENT_TIMESTAMP WHERE id = %s",
            (int(day), str(time_of_day), story_id),
            fetch="none", commit=True)

    def update_story_location(self, story_id, location):
        def fn(cur):
            cur.execute("SELECT metadata FROM stories WHERE id = %s", (story_id,))
            row = cur.fetchone()
            meta = (row["metadata"] if row and isinstance(row["metadata"], dict) else {}) or {}
            meta["current_location"] = location
            cur.execute("UPDATE stories SET metadata = %s, updated_at = CURRENT_TIMESTAMP WHERE id = %s",
                        (json.dumps(meta), story_id))
        self._with_conn(fn, commit=True)

    def update_character_stat(self, story_id, character_name, stat_name, new_value, max_value=100):
        def fn(cur):
            cur.execute(
                "SELECT id, metadata FROM story_characters WHERE story_id = %s AND LOWER(name) = LOWER(%s) LIMIT 1",
                (story_id, character_name))
            row = cur.fetchone()
            if not row: return False
            meta = (row["metadata"] if isinstance(row["metadata"], dict) else {}) or {}
            stats = meta.get("stats", {})
            stats[stat_name] = max(0, min(float(new_value), float(max_value)))
            meta["stats"] = stats
            cur.execute("UPDATE story_characters SET metadata = %s WHERE id = %s",
                        (json.dumps(meta), row["id"]))
            return True
        return self._with_conn(fn, commit=True) is True

db = Database()

try:
    db.init_tables()
except Exception as e:
    logger.error(f"DB init warning: {e}")
