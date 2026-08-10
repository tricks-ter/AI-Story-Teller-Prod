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
    VALID_TYPES = {"weapon", "armor", "accessory", "consumable", "material", "quest"}
    VALID_SLOTS = {"main_hand", "off_hand", "head", "body", "ring", "amulet", "trinket"}
    VALID_RARITIES = {"common", "uncommon", "rare", "epic", "legendary"}
    STACKABLE_TYPES = {"consumable", "material"}
    DEFAULT_SLOT = {"weapon": "main_hand", "armor": "body", "accessory": "trinket"}
    DEFAULT_ITEM_DESCRIPTIONS = {
        "Starter Item": "A humble keepsake from home — sentimental value only, but it steadies your resolve.",
        "Adventurer's Kit": "A worn satchel with rope, a waterskin, dried rations and a flint — the basics any traveler needs.",
    }

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
        if not self.database_url:
            logger.warning("DATABASE_URL not set — running without DB.")
            return
        row = self.execute_query("SELECT 1", fetch="one")
        if row is None:
            logger.warning("DB not reachable at boot.")

    @staticmethod
    def backpack_capacity(level):
        return 5 + int(level) * 5

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

    def delete_auth_token(self, token):
        self.execute_query("DELETE FROM auth_tokens WHERE token = %s", (token,), fetch="none", commit=True)

    def purge_expired_tokens(self):
        self.execute_query("DELETE FROM auth_tokens WHERE expires_at < CURRENT_TIMESTAMP", fetch="none", commit=True)

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

    def get_last_session_message(self, session_id):
        return self.execute_query(
            "SELECT role, content, created_at FROM chat_messages WHERE session_id = %s ORDER BY id DESC LIMIT 1",
            (session_id,), fetch="one")

    # ── Stories ──
    def create_story(self, story_id, title, genre, premise, metadata=None, creator_id=None, telemetry=None, is_public=True):
        if not self.database_url: return
        cid = creator_id or LEGACY_USER_ID
        merged = _merge_telemetry(metadata, telemetry, telemetry_key="created_telemetry")
        try:
            self.execute_query(
                "INSERT INTO stories (id, title, genre, premise, current_day, time_of_day, creator_id, "
                "is_premium, energy_cost, is_public, metadata, created_at, updated_at) "
                "VALUES (%s, %s, %s, %s, 1, 'Morning', %s, FALSE, 0, %s, %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
                (story_id, title, genre, premise, cid, bool(is_public), json.dumps(merged)),
                fetch="none", commit=True)
        except Exception:
            self.execute_query(
                "INSERT INTO stories (id, title, genre, premise, current_day, time_of_day, creator_id, "
                "is_premium, energy_cost, metadata, created_at, updated_at) "
                "VALUES (%s, %s, %s, %s, 1, 'Morning', %s, FALSE, 0, %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
                (story_id, title, genre, premise, cid, json.dumps(merged)),
                fetch="none", commit=True)

    def set_story_visibility(self, story_id, is_public):
        self.execute_query(
            "UPDATE stories SET is_public = %s, updated_at = CURRENT_TIMESTAMP WHERE id = %s",
            (bool(is_public), story_id), fetch="none", commit=True)

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
            "SELECT s.id, s.title, s.genre, s.premise, s.current_day, s.time_of_day, s.is_premium, s.is_public, s.updated_at, "
            "(SELECT sc.name FROM story_characters sc WHERE sc.story_id = s.id AND sc.is_player = TRUE ORDER BY sc.created_at ASC LIMIT 1) AS character_name, "
            "(SELECT sc.role FROM story_characters sc WHERE sc.story_id = s.id AND sc.is_player = TRUE ORDER BY sc.created_at ASC LIMIT 1) AS character_role "
            "FROM stories s WHERE s.creator_id = %s ORDER BY s.updated_at DESC",
            (user_id,), fetch="all") or []

    def list_all_stories(self, user_id):
        if not self.database_url: return []
        try:
            return self.execute_query(
                "SELECT s.id, s.title, s.genre, s.premise, s.is_premium, s.is_public, s.creator_id, s.updated_at, u.username AS creator_name, "
                "(SELECT sc.name FROM story_characters sc WHERE sc.story_id = s.id AND sc.is_player = TRUE ORDER BY sc.created_at ASC LIMIT 1) AS character_name, "
                "(SELECT sc.role FROM story_characters sc WHERE sc.story_id = s.id AND sc.is_player = TRUE ORDER BY sc.created_at ASC LIMIT 1) AS character_role, "
                "(SELECT COUNT(*) FROM playthroughs p WHERE p.story_id = s.id AND p.user_id = %s) AS played_count "
                "FROM stories s LEFT JOIN users u ON u.id = s.creator_id "
                "WHERE (s.is_public = TRUE OR s.creator_id = %s) "
                "ORDER BY s.updated_at DESC LIMIT 100",
                (user_id, user_id), fetch="all") or []
        except Exception:
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

    def get_story_messages(self, story_id, limit=50, base_only=True):
        query = ("SELECT id, role, content, message_type, created_at "
                 "FROM story_messages WHERE story_id = %s")
        params = [story_id]
        if base_only:
            query += " AND playthrough_id = 'legacy'"
        query += " ORDER BY id ASC LIMIT %s"
        params.append(int(limit))
        return self.execute_query(query, tuple(params), fetch="all") or []

    # ── Director's Notes ──
    def get_story_notes(self, story_id, active_only=True):
        query = "SELECT content, priority FROM story_notes WHERE story_id = %s"
        if active_only:
            query += " AND is_active = TRUE"
        query += " ORDER BY priority DESC, id ASC LIMIT 10"
        return self.execute_query(query, (story_id,), fetch="all") or []

    def list_story_notes_full(self, story_id):
        return self.execute_query(
            "SELECT id, content, priority, is_active, created_at FROM story_notes WHERE story_id = %s "
            "ORDER BY priority DESC, id ASC LIMIT 50",
            (story_id,), fetch="all") or []

    def add_story_note(self, story_id, content, priority=5, is_active=True):
        def fn(cur):
            cur.execute(
                "INSERT INTO story_notes (story_id, content, priority, is_active, created_at) "
                "VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP) RETURNING id",
                (story_id, content, int(priority), bool(is_active)))
            return cur.fetchone()["id"]
        return self._with_conn(fn, commit=True)

    def toggle_story_note(self, note_id, is_active):
        self.execute_query("UPDATE story_notes SET is_active = %s WHERE id = %s",
                           (bool(is_active), note_id), fetch="none", commit=True)

    def delete_story_note(self, note_id):
        self.execute_query("DELETE FROM story_notes WHERE id = %s", (note_id,), fetch="none", commit=True)

    # ── Playthroughs ──
    def get_active_playthrough(self, story_id, user_id):
        return self.execute_query(
            "SELECT * FROM playthroughs WHERE story_id = %s AND user_id = %s AND status = 'active' "
            "ORDER BY updated_at DESC LIMIT 1",
            (story_id, user_id), fetch="one")

    def get_playthrough(self, playthrough_id):
        return self.execute_query(
            "SELECT * FROM playthroughs WHERE id = %s", (playthrough_id,), fetch="one")

    def complete_playthrough(self, playthrough_id):
        self.execute_query(
            "UPDATE playthroughs SET status = 'completed', updated_at = CURRENT_TIMESTAMP WHERE id = %s",
            (playthrough_id,), fetch="none", commit=True)

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
            cur.execute(
                "INSERT INTO story_messages (story_id, playthrough_id, role, content, message_type, metadata, created_at) "
                "SELECT %s, %s, role, content, message_type, metadata, CURRENT_TIMESTAMP "
                "FROM story_messages WHERE story_id = %s AND playthrough_id = 'legacy'",
                (story_id, pid, story_id))
            cur.execute(
                "INSERT INTO playthrough_backpacks (id, playthrough_id, character_id, level, metadata, created_at, updated_at) "
                "SELECT substr(md5(random()::text || pc.id), 1, 36), %s, pc.id, 1, '{}', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP "
                "FROM playthrough_characters pc WHERE pc.playthrough_id = %s",
                (pid, pid))
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

    def get_last_playthrough_message(self, playthrough_id):
        return self.execute_query(
            "SELECT role, content, created_at FROM story_messages WHERE playthrough_id = %s ORDER BY id DESC LIMIT 1",
            (playthrough_id,), fetch="one")

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

    # ── State updates ──
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
            return True
        self._with_conn(fn, commit=True)

    def upsert_playthrough_location(self, playthrough_id, location_name, description=""):
        desc = description or ""
        def fn(cur):
            loc_id = str(uuid.uuid4())
            cur.execute("SAVEPOINT loc_upsert")
            try:
                cur.execute(
                    "INSERT INTO locations (id, playthrough_id, name, description, is_discovered, visit_count, last_visited_at, metadata, created_at, updated_at) "
                    "VALUES (%s, %s, %s, %s, TRUE, 1, CURRENT_TIMESTAMP, '{}', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP) "
                    "ON CONFLICT (playthrough_id, LOWER(name)) DO UPDATE SET is_discovered = TRUE, "
                    "visit_count = locations.visit_count + 1, last_visited_at = CURRENT_TIMESTAMP, "
                    "description = CASE WHEN COALESCE(locations.description, '') = '' AND %s <> '' THEN %s ELSE locations.description END, "
                    "updated_at = CURRENT_TIMESTAMP",
                    (loc_id, playthrough_id, location_name, desc, desc, desc))
                cur.execute("RELEASE SAVEPOINT loc_upsert")
            except Exception:
                cur.execute("ROLLBACK TO SAVEPOINT loc_upsert")
                cur.execute(
                    "SELECT id, description FROM locations WHERE playthrough_id = %s AND LOWER(name) = LOWER(%s)",
                    (playthrough_id, location_name))
                row = cur.fetchone()
                if row:
                    new_desc = desc if not (row["description"] or "") else row["description"]
                    cur.execute(
                        "UPDATE locations SET is_discovered = TRUE, visit_count = visit_count + 1, last_visited_at = CURRENT_TIMESTAMP, description = %s, updated_at = CURRENT_TIMESTAMP WHERE id = %s",
                        (new_desc, row["id"]))
                else:
                    cur.execute(
                        "INSERT INTO locations (id, playthrough_id, name, description, is_discovered, visit_count, last_visited_at, metadata, created_at, updated_at) "
                        "VALUES (%s, %s, %s, %s, TRUE, 1, CURRENT_TIMESTAMP, '{}', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
                        (loc_id, playthrough_id, location_name, desc))

            cur.execute("SELECT metadata FROM playthroughs WHERE id = %s", (playthrough_id,))
            pt_row = cur.fetchone()
            meta = (pt_row["metadata"] if pt_row and isinstance(pt_row["metadata"], dict) else {}) or {}
            meta["current_location"] = location_name
            cur.execute("UPDATE playthroughs SET metadata = %s, updated_at = CURRENT_TIMESTAMP WHERE id = %s",
                        (json.dumps(meta), playthrough_id))
            return True
        return self._with_conn(fn, commit=True) is True

    def get_playthrough_locations(self, playthrough_id):
        return self.execute_query(
            "SELECT id, name, description, is_discovered, metadata, created_at, updated_at "
            "FROM locations WHERE playthrough_id = %s ORDER BY updated_at DESC",
            (playthrough_id,), fetch="all") or []

    def get_playthrough_map(self, playthrough_id):
        return self.execute_query(
            "SELECT id, name, description, visit_count, is_discovered, created_at, last_visited_at "
            "FROM locations WHERE playthrough_id = %s ORDER BY created_at ASC",
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

    def update_playthrough_character_ability(self, playthrough_id, character_id, ability_name, add=True, description=""):
        def fn(cur):
            cur.execute(
                "SELECT id, metadata FROM playthrough_characters WHERE id = %s AND playthrough_id = %s",
                (character_id, playthrough_id))
            row = cur.fetchone()
            if not row: return False
            meta = (row["metadata"] if isinstance(row["metadata"], dict) else {}) or {}
            abilities = meta.get("abilities", [])
            if not isinstance(abilities, list): abilities = []
            if add:
                existing = next((a for a in abilities if isinstance(a, dict) and str(a.get("name", "")).lower() == ability_name.lower()), None)
                if existing:
                    if description: existing["description"] = description
                else:
                    abilities.append({"name": ability_name, "description": description or ""})
            else:
                abilities = [a for a in abilities if not (isinstance(a, dict) and str(a.get("name", "")).lower() == ability_name.lower())]
            meta["abilities"] = abilities
            cur.execute("UPDATE playthrough_characters SET metadata = %s WHERE id = %s",
                        (json.dumps(meta), row["id"]))
            return True
        return self._with_conn(fn, commit=True) is True

    def update_playthrough_character_inventory(self, playthrough_id, character_name, item_name, add=True):
        def fn(cur):
            cur.execute(
                "SELECT id, metadata FROM playthrough_characters WHERE playthrough_id = %s AND LOWER(character_name) = LOWER(%s) LIMIT 1",
                (playthrough_id, character_name))
            row = cur.fetchone()
            if not row: return False
            self._sync_inventory_mirror(cur, row["id"], item_name, add)
            return True
        return self._with_conn(fn, commit=True) is True

    def _sync_inventory_mirror(self, cur, character_id, name, add):
        cur.execute("SELECT metadata FROM playthrough_characters WHERE id = %s", (character_id,))
        row = cur.fetchone()
        if not row: return
        meta = (row["metadata"] if isinstance(row["metadata"], dict) else {}) or {}
        inv = meta.get("inventory", [])
        if not isinstance(inv, list): inv = []
        present = any(str(i).lower() == str(name).lower() for i in inv)
        if add and not present:
            inv.append(name)
        elif not add and present:
            inv = [i for i in inv if str(i).lower() != str(name).lower()]
        meta["inventory"] = inv
        cur.execute("UPDATE playthrough_characters SET metadata = %s WHERE id = %s",
                    (json.dumps(meta), character_id))

    # ── Inventory / Equipment / Backpacks ──
    def ensure_playthrough_inventory(self, playthrough_id):
        def fn(cur):
            cur.execute("SELECT id, metadata FROM playthrough_characters WHERE playthrough_id = %s", (playthrough_id,))
            chars = cur.fetchall() or []
            for c in chars:
                cur.execute("SELECT id FROM playthrough_backpacks WHERE character_id = %s", (c["id"],))
                if not cur.fetchone():
                    cur.execute(
                        "INSERT INTO playthrough_backpacks (id, playthrough_id, character_id, level, metadata, created_at, updated_at) "
                        "VALUES (%s, %s, %s, 1, '{}', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
                        (str(uuid.uuid4()), playthrough_id, c["id"]))
                cur.execute("SELECT id FROM playthrough_items WHERE character_id = %s LIMIT 1", (c["id"],))
                if not cur.fetchone():
                    meta = (c["metadata"] if isinstance(c["metadata"], dict) else {}) or {}
                    inv = meta.get("inventory", [])
                    if isinstance(inv, list):
                        for name in inv:
                            if isinstance(name, str) and name.strip():
                                desc = self.DEFAULT_ITEM_DESCRIPTIONS.get(name.strip(), "")
                                cur.execute(
                                    "INSERT INTO playthrough_items (id, playthrough_id, character_id, name, item_type, slot, rarity, item_level, weight, quantity, metadata, created_at, updated_at) "
                                    "VALUES (%s, %s, %s, %s, 'material', '', 'common', 1, 1, 1, %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
                                    (str(uuid.uuid4()), playthrough_id, c["id"], name.strip(), json.dumps({"description": desc})))
                for dname, ddesc in self.DEFAULT_ITEM_DESCRIPTIONS.items():
                    cur.execute(
                        "UPDATE playthrough_items SET metadata = COALESCE(metadata, '{}') || %s::jsonb, updated_at = CURRENT_TIMESTAMP "
                        "WHERE character_id = %s AND LOWER(name) = LOWER(%s) AND COALESCE(metadata->>'description', '') = ''",
                        (json.dumps({"description": ddesc}), c["id"], dname))
            return True
        return self._with_conn(fn, commit=True) is True

    def get_backpack_for_character(self, character_id):
        return self.execute_query(
            "SELECT id, playthrough_id, character_id, level, metadata FROM playthrough_backpacks WHERE character_id = %s",
            (character_id,), fetch="one")

    def list_playthrough_backpacks(self, playthrough_id):
        return self.execute_query(
            "SELECT id, playthrough_id, character_id, level, metadata FROM playthrough_backpacks WHERE playthrough_id = %s",
            (playthrough_id,), fetch="all") or []

    def backpack_used_capacity(self, character_id):
        row = self.execute_query(
            "SELECT COALESCE(SUM(weight * quantity), 0) AS used FROM playthrough_items "
            "WHERE character_id = %s AND id NOT IN (SELECT item_id FROM playthrough_equipment WHERE character_id = %s)",
            (character_id, character_id), fetch="one")
        return int(row["used"]) if row else 0

    def list_playthrough_items(self, playthrough_id):
        return self.execute_query(
            "SELECT id, playthrough_id, character_id, name, item_type, slot, rarity, item_level, weight, quantity, metadata, created_at "
            "FROM playthrough_items WHERE playthrough_id = %s ORDER BY created_at ASC",
            (playthrough_id,), fetch="all") or []

    def list_carried_items_for_character(self, character_id):
        return self.execute_query(
            "SELECT name, quantity, item_type FROM playthrough_items "
            "WHERE character_id = %s AND id NOT IN (SELECT item_id FROM playthrough_equipment WHERE character_id = %s) "
            "ORDER BY created_at ASC",
            (character_id, character_id), fetch="all") or []

    def list_playthrough_equipment(self, playthrough_id):
        return self.execute_query(
            "SELECT pe.id, pe.character_id, pe.item_id, pe.slot, pi.name AS item_name, pi.rarity, pi.item_level "
            "FROM playthrough_equipment pe JOIN playthrough_items pi ON pi.id = pe.item_id "
            "WHERE pe.playthrough_id = %s ORDER BY pe.slot ASC",
            (playthrough_id,), fetch="all") or []

    def list_equipment_for_character(self, character_id):
        return self.execute_query(
            "SELECT pe.id, pe.character_id, pe.item_id, pe.slot, pi.name AS item_name, pi.rarity, pi.item_level "
            "FROM playthrough_equipment pe JOIN playthrough_items pi ON pi.id = pe.item_id "
            "WHERE pe.character_id = %s ORDER BY pe.slot ASC",
            (character_id,), fetch="all") or []

    def compute_equipped_bonuses(self, character_id):
        rows = self.execute_query(
            "SELECT pi.metadata FROM playthrough_equipment pe JOIN playthrough_items pi ON pi.id = pe.item_id "
            "WHERE pe.character_id = %s",
            (character_id,), fetch="all") or []
        totals = {}
        for r in rows:
            meta = (r["metadata"] if isinstance(r["metadata"], dict) else {}) or {}
            bonuses = meta.get("bonuses", {})
            if isinstance(bonuses, dict):
                for k, v in bonuses.items():
                    try:
                        totals[k] = totals.get(k, 0) + float(v)
                    except Exception:
                        pass
        return totals

    def set_playthrough_backpack_level(self, playthrough_id, character_id, level):
        lvl = max(1, min(20, int(level)))
        def fn(cur):
            cur.execute("SELECT id FROM playthrough_backpacks WHERE character_id = %s", (character_id,))
            row = cur.fetchone()
            if row:
                cur.execute("UPDATE playthrough_backpacks SET level = %s, updated_at = CURRENT_TIMESTAMP WHERE id = %s",
                            (lvl, row["id"]))
            else:
                cur.execute(
                    "INSERT INTO playthrough_backpacks (id, playthrough_id, character_id, level, metadata, created_at, updated_at) "
                    "VALUES (%s, %s, %s, %s, '{}', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
                    (str(uuid.uuid4()), playthrough_id, character_id, lvl))
            return True
        return self._with_conn(fn, commit=True) is True

    def grant_playthrough_item(self, playthrough_id, character_id, name, attrs=None):
        attrs = attrs or {}
        itype = attrs.get("type") if attrs.get("type") in self.VALID_TYPES else "material"
        slot = attrs.get("slot") if attrs.get("slot") in self.VALID_SLOTS else (self.DEFAULT_SLOT.get(itype, "") if itype in self.DEFAULT_SLOT else "")
        rarity = attrs.get("rarity") if attrs.get("rarity") in self.VALID_RARITIES else "common"
        level = max(1, min(99, int(attrs.get("level", 1) or 1)))
        weight = max(0, min(99, int(attrs.get("weight", 1) if attrs.get("weight") is not None else 1)))
        bonuses = attrs.get("bonuses") if isinstance(attrs.get("bonuses"), dict) else {}
        description = attrs.get("description", "") or self.DEFAULT_ITEM_DESCRIPTIONS.get(name, "")
        stackable = itype in self.STACKABLE_TYPES

        def fn(cur):
            cur.execute("SELECT level FROM playthrough_backpacks WHERE character_id = %s", (character_id,))
            bp = cur.fetchone()
            if not bp:
                cur.execute(
                    "INSERT INTO playthrough_backpacks (id, playthrough_id, character_id, level, metadata, created_at, updated_at) "
                    "VALUES (%s, %s, %s, 1, '{}', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
                    (str(uuid.uuid4()), playthrough_id, character_id))
                bp_level = 1
            else:
                bp_level = bp["level"]
            cap = self.backpack_capacity(bp_level)
            cur.execute(
                "SELECT COALESCE(SUM(weight * quantity), 0) AS used FROM playthrough_items "
                "WHERE character_id = %s AND id NOT IN (SELECT item_id FROM playthrough_equipment WHERE character_id = %s)",
                (character_id, character_id))
            used = int(cur.fetchone()["used"])
            if used + weight > cap:
                return {"ok": False, "reason": "backpack_full"}

            if stackable:
                cur.execute(
                    "SELECT id, quantity FROM playthrough_items WHERE character_id = %s AND LOWER(name) = LOWER(%s) AND item_type = %s LIMIT 1",
                    (character_id, name, itype))
                row = cur.fetchone()
                if row:
                    cur.execute("UPDATE playthrough_items SET quantity = LEAST(99, quantity + 1), updated_at = CURRENT_TIMESTAMP WHERE id = %s", (row["id"],))
                    self._sync_inventory_mirror(cur, character_id, name, True)
                    return {"ok": True}

            meta = {"description": description}
            if bonuses: meta["bonuses"] = bonuses
            cur.execute(
                "INSERT INTO playthrough_items (id, playthrough_id, character_id, name, item_type, slot, rarity, item_level, weight, quantity, metadata, created_at, updated_at) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 1, %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
                (str(uuid.uuid4()), playthrough_id, character_id, name, itype, slot, rarity, level, weight, json.dumps(meta)))
            self._sync_inventory_mirror(cur, character_id, name, True)
            return {"ok": True}
        return self._with_conn(fn, commit=True) or {"ok": False, "reason": "db_error"}

    def consume_playthrough_item(self, playthrough_id, character_id, name):
        def fn(cur):
            cur.execute(
                "SELECT id, quantity FROM playthrough_items WHERE character_id = %s AND LOWER(name) = LOWER(%s) ORDER BY created_at ASC LIMIT 1",
                (character_id, name))
            row = cur.fetchone()
            if not row: return False
            cur.execute("DELETE FROM playthrough_equipment WHERE item_id = %s", (row["id"],))
            if int(row["quantity"]) <= 1:
                cur.execute("DELETE FROM playthrough_items WHERE id = %s", (row["id"],))
                self._sync_inventory_mirror(cur, character_id, name, False)
            else:
                cur.execute("UPDATE playthrough_items SET quantity = quantity - 1, updated_at = CURRENT_TIMESTAMP WHERE id = %s", (row["id"],))
            return True
        return self._with_conn(fn, commit=True) is True

    def use_item(self, playthrough_id, character_id, item_id):
        def fn(cur):
            cur.execute("SELECT * FROM playthrough_items WHERE id = %s AND playthrough_id = %s", (item_id, playthrough_id))
            item = cur.fetchone()
            if not item: return {"ok": False, "reason": "not_found"}
            if item["character_id"] != character_id: return {"ok": False, "reason": "not_owner"}
            if item["item_type"] != "consumable": return {"ok": False, "reason": "not_usable"}
            cur.execute("DELETE FROM playthrough_equipment WHERE item_id = %s", (item_id,))
            if int(item["quantity"]) <= 1:
                cur.execute("DELETE FROM playthrough_items WHERE id = %s", (item_id,))
                self._sync_inventory_mirror(cur, character_id, item["name"], False)
            else:
                cur.execute("UPDATE playthrough_items SET quantity = quantity - 1, updated_at = CURRENT_TIMESTAMP WHERE id = %s", (item_id,))
            return {"ok": True, "name": item["name"]}
        return self._with_conn(fn, commit=True) or {"ok": False, "reason": "db_error"}

    def drop_item(self, playthrough_id, character_id, item_id):
        def fn(cur):
            cur.execute("SELECT * FROM playthrough_items WHERE id = %s AND playthrough_id = %s", (item_id, playthrough_id))
            item = cur.fetchone()
            if not item: return {"ok": False, "reason": "not_found"}
            if item["character_id"] != character_id: return {"ok": False, "reason": "not_owner"}
            if item["item_type"] == "quest": return {"ok": False, "reason": "quest_locked"}
            cur.execute("DELETE FROM playthrough_equipment WHERE item_id = %s", (item_id,))
            cur.execute("DELETE FROM playthrough_items WHERE id = %s", (item_id,))
            self._sync_inventory_mirror(cur, character_id, item["name"], False)
            return {"ok": True, "name": item["name"]}
        return self._with_conn(fn, commit=True) or {"ok": False, "reason": "db_error"}

    def equip_item(self, playthrough_id, character_id, item_id):
        def fn(cur):
            cur.execute("SELECT * FROM playthrough_items WHERE id = %s AND playthrough_id = %s", (item_id, playthrough_id))
            item = cur.fetchone()
            if not item: return {"ok": False, "reason": "not_found"}
            if item["character_id"] != character_id: return {"ok": False, "reason": "not_owner"}
            slot = item["slot"]
            if not slot: return {"ok": False, "reason": "not_equippable"}

            cur.execute("SELECT level FROM playthrough_backpacks WHERE character_id = %s", (character_id,))
            bp = cur.fetchone()
            cap = self.backpack_capacity(bp["level"]) if bp else 10
            cur.execute(
                "SELECT COALESCE(SUM(weight * quantity), 0) AS used FROM playthrough_items "
                "WHERE character_id = %s AND id NOT IN (SELECT item_id FROM playthrough_equipment WHERE character_id = %s)",
                (character_id, character_id))
            used = int(cur.fetchone()["used"])

            cur.execute("SELECT item_id FROM playthrough_equipment WHERE character_id = %s AND slot = %s", (character_id, slot))
            old = cur.fetchone()
            old_weight = 0
            if old:
                cur.execute("SELECT weight FROM playthrough_items WHERE id = %s", (old["item_id"],))
                ow = cur.fetchone()
                old_weight = int(ow["weight"]) if ow else 0

            if used - int(item["weight"]) + old_weight > cap:
                return {"ok": False, "reason": "backpack_full"}

            if old:
                cur.execute("DELETE FROM playthrough_equipment WHERE id = %s", (old["id"],))
            cur.execute(
                "INSERT INTO playthrough_equipment (id, playthrough_id, character_id, item_id, slot, created_at) "
                "VALUES (%s, %s, %s, %s, %s, CURRENT_TIMESTAMP)",
                (str(uuid.uuid4()), playthrough_id, character_id, item_id, slot))
            return {"ok": True}
        return self._with_conn(fn, commit=True) or {"ok": False, "reason": "db_error"}

    def unequip_item(self, playthrough_id, character_id, item_id):
        def fn(cur):
            cur.execute("SELECT * FROM playthrough_items WHERE id = %s AND playthrough_id = %s", (item_id, playthrough_id))
            item = cur.fetchone()
            if not item: return {"ok": False, "reason": "not_found"}
            if item["character_id"] != character_id: return {"ok": False, "reason": "not_owner"}
            cur.execute("SELECT id FROM playthrough_equipment WHERE item_id = %s AND character_id = %s", (item_id, character_id))
            eq = cur.fetchone()
            if not eq: return {"ok": False, "reason": "not_equipped"}

            cur.execute("SELECT level FROM playthrough_backpacks WHERE character_id = %s", (character_id,))
            bp = cur.fetchone()
            cap = self.backpack_capacity(bp["level"]) if bp else 10
            cur.execute(
                "SELECT COALESCE(SUM(weight * quantity), 0) AS used FROM playthrough_items "
                "WHERE character_id = %s AND id NOT IN (SELECT item_id FROM playthrough_equipment WHERE character_id = %s)",
                (character_id, character_id))
            used = int(cur.fetchone()["used"])
            if used + int(item["weight"]) > cap:
                return {"ok": False, "reason": "backpack_full"}

            cur.execute("DELETE FROM playthrough_equipment WHERE id = %s", (eq["id"],))
            return {"ok": True}
        return self._with_conn(fn, commit=True) or {"ok": False, "reason": "db_error"}

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
            return True
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

    # ── Phase 6 UI: story & character art (appended inside class-safe zone) ──
def set_story_art(story_id, kind, data_url):
    col = "cover_image" if kind == "cover" else "banner_image"
    db.execute_query(
        "UPDATE stories SET " + col + " = %s, updated_at = CURRENT_TIMESTAMP WHERE id = %s",
        (data_url, story_id), fetch="none", commit=True)
    return True

def set_character_image(character_id, data_url):
    db.execute_query(
        "UPDATE story_characters SET image = %s WHERE id = %s",
        (data_url, character_id), fetch="none", commit=True)
    return True

def get_stories_art(ids):
    if not ids:
        return {}
    rows = db.execute_query(
        "SELECT id, cover_image, banner_image FROM stories WHERE id = ANY(%s)",
        (list(ids),), fetch="all")
    if rows is None:  # pre-migration fallback (rule 8)
        return {i: {"cover_image": "", "banner_image": ""} for i in ids}
    return {r["id"]: {"cover_image": r.get("cover_image") or "", "banner_image": r.get("banner_image") or ""} for r in rows}

def get_cast_with_images(story_id):
    rows = db.execute_query(
        "SELECT id, name, role, background, is_player, image FROM story_characters "
        "WHERE story_id = %s ORDER BY is_player DESC, created_at ASC",
        (story_id,), fetch="all")
    if rows is None:  # pre-migration fallback
        return db.get_story_characters(story_id)
    return [dict(r, image=r.get("image") or "") for r in rows]

    def update_story_metadata(self, story_id, title, genre, premise, is_public):
        try:
            self.execute_query(
                "UPDATE stories SET title = %s, genre = %s, premise = %s, is_public = %s, updated_at = CURRENT_TIMESTAMP WHERE id = %s",
                (title, genre, premise, bool(is_public), story_id),
                fetch="none", commit=True)
        except Exception:
            self.execute_query(
                "UPDATE stories SET title = %s, genre = %s, premise = %s, updated_at = CURRENT_TIMESTAMP WHERE id = %s",
                (title, genre, premise, story_id),
                fetch="none", commit=True)

    def update_story_metadata(self, story_id, title, genre, premise, is_public):
        try:
            self.execute_query(
                "UPDATE stories SET title = %s, genre = %s, premise = %s, is_public = %s, updated_at = CURRENT_TIMESTAMP WHERE id = %s",
                (title, genre, premise, bool(is_public), story_id),
                fetch="none", commit=True)
        except Exception:
            self.execute_query(
                "UPDATE stories SET title = %s, genre = %s, premise = %s, updated_at = CURRENT_TIMESTAMP WHERE id = %s",
                (title, genre, premise, story_id),
                fetch="none", commit=True)

    # ── N+1 Query Eliminator ──
    def get_full_playthrough_state(self, playthrough_id):
        chars = self.get_playthrough_characters(playthrough_id)
        if not chars: return {"characters": [], "items": [], "equipment": [], "backpacks": []}
        
        items = self.execute_query(
            "SELECT id, character_id, name, item_type, slot, rarity, item_level, weight, quantity, metadata "
            "FROM playthrough_items WHERE playthrough_id = %s",
            (playthrough_id,), fetch="all") or []
            
        equipment = self.execute_query(
            "SELECT pe.character_id, pe.item_id, pe.slot, pi.name AS item_name, pi.rarity, pi.item_level, pi.metadata "
            "FROM playthrough_equipment pe JOIN playthrough_items pi ON pi.id = pe.item_id "
            "WHERE pe.playthrough_id = %s",
            (playthrough_id,), fetch="all") or []
            
        backpacks = self.execute_query(
            "SELECT id, character_id, level FROM playthrough_backpacks WHERE playthrough_id = %s",
            (playthrough_id,), fetch="all") or []
            
        return {"characters": chars, "items": items, "equipment": equipment, "backpacks": backpacks}

    # ── Phase 6: Memory, Lorebook, and Nudges ──
    def get_recent_messages_for_context(self, playthrough_id, max_chars=40000):
        msgs = self.execute_query(
            "SELECT id, role, content FROM story_messages WHERE playthrough_id = %s ORDER BY id ASC",
            (playthrough_id,), fetch="all") or []
        
        selected = []
        current_chars = 0
        # Build from the end backwards to prioritize recent context
        for m in reversed(msgs):
            msg_len = len(m["content"]) + 10 # overhead for role formatting
            if current_chars + msg_len > max_chars and selected:
                break
            selected.append(m)
            current_chars += msg_len
            
        return list(reversed(selected))

    def update_memory_summary(self, playthrough_id, summary):
        self.execute_query(
            "UPDATE playthroughs SET memory_summary = %s, updated_at = CURRENT_TIMESTAMP WHERE id = %s",
            (summary, playthrough_id), fetch="none", commit=True)

    def get_memory_summary(self, playthrough_id):
        row = self.execute_query("SELECT memory_summary FROM playthroughs WHERE id = %s", (playthrough_id,), fetch="one")
        return row["memory_summary"] if row and row.get("memory_summary") else ""

    def append_lorebook_entry(self, playthrough_id, entry_dict):
        def fn(cur):
            cur.execute("SELECT lorebook FROM playthroughs WHERE id = %s", (playthrough_id,))
            row = cur.fetchone()
            lore = row["lorebook"] if row and isinstance(row.get("lorebook"), list) else []
            if "title" in entry_dict:
                lore = [l for l in lore if l.get("title") != entry_dict["title"]]
            lore.append(entry_dict)
            lore = lore[-50:] # Keep last 50 entries
            cur.execute("UPDATE playthroughs SET lorebook = %s, updated_at = CURRENT_TIMESTAMP WHERE id = %s",
                        (json.dumps(lore), playthrough_id))
        self._with_conn(fn, commit=True)

    def get_lorebook(self, playthrough_id):
        row = self.execute_query("SELECT lorebook FROM playthroughs WHERE id = %s", (playthrough_id,), fetch="one")
        return row["lorebook"] if row and isinstance(row.get("lorebook"), list) else []

    def set_active_nudge(self, playthrough_id, nudge):
        self.execute_query(
            "UPDATE playthroughs SET active_nudge = %s, updated_at = CURRENT_TIMESTAMP WHERE id = %s",
            (nudge, playthrough_id), fetch="none", commit=True)

    def get_and_clear_nudge(self, playthrough_id):
        def fn(cur):
            cur.execute("SELECT active_nudge FROM playthroughs WHERE id = %s", (playthrough_id,))
            row = cur.fetchone()
            nudge = row["active_nudge"] if row and row.get("active_nudge") else ""
            if nudge:
                cur.execute("UPDATE playthroughs SET active_nudge = '' WHERE id = %s", (playthrough_id,))
            return nudge
        return self._with_conn(fn, commit=True) or ""
