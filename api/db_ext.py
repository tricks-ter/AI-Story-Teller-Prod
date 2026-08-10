"""Phase 7B additive module: story art + living-world state + event ledger.
Kept separate from database.py to stay purely additive (no rewrite risk)."""
import json
import uuid
import logging
from database import db

logger = logging.getLogger(__name__)

VALID_NODE_TYPES = {"region", "faction", "settlement", "location", "npc", "item", "economy_state"}

# ── Story Art ──
def set_story_art(story_id, cover_image):
    try:
        db.execute_query(
            "UPDATE stories SET cover_image = %s, updated_at = CURRENT_TIMESTAMP WHERE id = %s",
            (cover_image or "", story_id), fetch="none", commit=True)
        return True
    except Exception as e:
        logger.error(f"set_story_art failed: {e}")
        return False

def get_all_story_art():
    try:
        rows = db.execute_query("SELECT id, cover_image FROM stories WHERE COALESCE(cover_image, '') <> ''") or []
        return {r["id"]: r["cover_image"] for r in rows}
    except Exception:
        return {}

def set_character_image(story_id, character_name, image):
    db.execute_query(
        "UPDATE story_characters SET image = %s WHERE story_id = %s AND LOWER(name) = LOWER(%s)",
        (image or "", story_id, character_name), fetch="none", commit=True)

def get_cast_with_images(story_id):
    return db.execute_query(
        "SELECT id, name, role, image FROM story_characters WHERE story_id = %s "
        "ORDER BY is_player DESC, created_at ASC", (story_id,), fetch="all") or []

# ── Living World: nodes with state ──
def get_world_nodes_full(playthrough_id):
    try:
        return db.execute_query(
            "SELECT id, parent_id, node_type, name, metadata, status, is_alive, relationship, wealth, power, allegiance "
            "FROM world_nodes WHERE playthrough_id = %s ORDER BY created_at ASC",
            (playthrough_id,), fetch="all") or []
    except Exception:
        return db.get_world_nodes(playthrough_id)

def update_world_node_state(playthrough_id, node_name, updates):
    """Upsert an entity and apply state changes. Signed values = deltas."""
    try:
        def fn(cur):
            cur.execute(
                "SELECT id, node_type, relationship, wealth, power FROM world_nodes "
                "WHERE playthrough_id = %s AND LOWER(name) = LOWER(%s) LIMIT 1",
                (playthrough_id, node_name))
            row = cur.fetchone()
            created = False
            if not row:
                kind = str(updates.get("kind", "")).lower()
                if kind not in VALID_NODE_TYPES:
                    kind = "npc" if (updates.get("is_alive") is not None or updates.get("relationship") is not None) else "faction"
                new_id = str(uuid.uuid4())
                cur.execute(
                    "INSERT INTO world_nodes (id, playthrough_id, parent_id, node_type, name, metadata, "
                    "status, is_alive, relationship, wealth, power, allegiance, created_at, updated_at) "
                    "VALUES (%s, %s, NULL, %s, %s, '{}', 'stable', TRUE, 0, 0, 50, '', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
                    (new_id, playthrough_id, kind, node_name))
                row = {"id": new_id, "relationship": 0, "wealth": 0, "power": 50}
                created = True

            sets, params = [], []
            if updates.get("status"):
                sets.append("status = %s"); params.append(str(updates["status"])[:64])
            if updates.get("allegiance"):
                sets.append("allegiance = %s"); params.append(str(updates["allegiance"])[:255])
            if "is_alive" in updates and updates["is_alive"] is not None:
                sets.append("is_alive = %s"); params.append(bool(updates["is_alive"]))
            for k in ("relationship", "power", "wealth"):
                raw = updates.get(k)
                if raw in (None, ""):
                    continue
                try:
                    raw_s = str(raw).strip()
                    delta = raw_s.startswith(("+", "-"))
                    v = int(float(raw_s))
                    cur_v = int(row.get(k) or 0)
                    new_v = cur_v + v if delta else v
                    if k == "relationship": new_v = max(-100, min(100, new_v))
                    if k == "power": new_v = max(0, min(100, new_v))
                    if k == "wealth": new_v = max(0, min(9999999, new_v))
                    sets.append(f"{k} = %s"); params.append(new_v)
                except Exception:
                    pass
            if sets:
                sets.append("last_state_change_at = CURRENT_TIMESTAMP")
                sets.append("updated_at = CURRENT_TIMESTAMP")
                params.append(row["id"])
                cur.execute(f"UPDATE world_nodes SET {', '.join(sets)} WHERE id = %s", tuple(params))
            return {"ok": True, "created": created}
        return db._with_conn(fn, commit=True) or {"ok": False, "reason": "db_error"}
    except Exception as e:
        logger.error(f"world state update failed: {e}")
        return {"ok": False, "reason": "internal_error"}

# ── World Event Ledger ──
def record_world_event(playthrough_id, node_name, event_type, description, day):
    def fn(cur):
        cur.execute(
            "SELECT id FROM world_nodes WHERE playthrough_id = %s AND LOWER(name) = LOWER(%s) LIMIT 1",
            (playthrough_id, node_name or ""))
        row = cur.fetchone()
        cur.execute(
            "INSERT INTO world_events (id, playthrough_id, node_id, node_name, event_type, description, day, created_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)",
            (str(uuid.uuid4()), playthrough_id, row["id"] if row else "",
             node_name or "The World", (event_type or "event")[:32], description or "", int(day or 1)))
        return True
    return db._with_conn(fn, commit=True) is True

def get_recent_world_events(playthrough_id, limit=10):
    try:
        return db.execute_query(
            "SELECT id, node_id, node_name, event_type, description, day FROM world_events "
            "WHERE playthrough_id = %s ORDER BY day DESC, created_at DESC LIMIT %s",
            (playthrough_id, int(limit)), fetch="all") or []
    except Exception:
        return []

# ── Memory ──
def set_memory_summary(playthrough_id, summary):
    def fn(cur):
        cur.execute("SELECT metadata FROM playthroughs WHERE id = %s", (playthrough_id,))
        row = cur.fetchone()
        if not row: return False
        meta = (row["metadata"] if isinstance(row["metadata"], dict) else {}) or {}
        meta["memory_summary"] = summary or ""
        cur.execute("UPDATE playthroughs SET metadata = %s, updated_at = CURRENT_TIMESTAMP WHERE id = %s",
                    (json.dumps(meta), playthrough_id))
        return True
    return db._with_conn(fn, commit=True) is True
