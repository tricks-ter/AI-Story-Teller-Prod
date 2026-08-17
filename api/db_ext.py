"""Phase 7B additive module: story art, story metadata edits, living-world state,
world event ledger, inventory dedupe/stacking, memory summaries.
Kept separate from database.py to stay purely additive (no rewrite risk)."""
import json
import uuid
import logging
from database import db, LEGACY_USER_ID

logger = logging.getLogger(__name__)

VALID_NODE_TYPES = {"region", "faction", "settlement", "location", "npc", "item", "economy_state"}
STACKABLE_TYPES = {"consumable", "material"}

# ── Story Art & Metadata ──
def set_story_art(story_id, cover_image):
    try:
        db.execute_query(
            "UPDATE stories SET cover_image = %s, updated_at = CURRENT_TIMESTAMP WHERE id = %s",
            (cover_image or "", story_id), fetch="none", commit=True)
        return True
    except Exception as e:
        logger.error(f"set_story_art failed: {e}")
        return False

def set_story_banner(story_id, banner_image):
    try:
        db.execute_query(
            "UPDATE stories SET banner_image = %s, updated_at = CURRENT_TIMESTAMP WHERE id = %s",
            (banner_image or "", story_id), fetch="none", commit=True)
        return True
    except Exception as e:
        logger.error(f"set_story_banner failed: {e}")
        return False

def get_all_story_art():
    try:
        rows = db.execute_query("SELECT id, cover_image, banner_image FROM stories WHERE COALESCE(cover_image, '') <> '' OR COALESCE(banner_image, '') <> ''") or []
        return {r["id"]: {"cover": r["cover_image"], "banner": r["banner_image"]} for r in rows}
    except Exception:
        return {}

def set_character_image(story_id, character_name, image):
    db.execute_query(
        "UPDATE story_characters SET image = %s WHERE story_id = %s AND LOWER(name) = LOWER(%s)",
        (image or "", story_id, character_name), fetch="none", commit=True)

def set_character_image_by_id(story_id, char_id, image):
    """Portrait upload by character id, scoped to the story. False if not found."""
    try:
        row = db.execute_query(
            "SELECT id FROM story_characters WHERE id = %s AND story_id = %s",
            (char_id, story_id), fetch="one")
        if not row:
            return False
        db.execute_query(
            "UPDATE story_characters SET image = %s WHERE id = %s",
            (image or "", char_id), fetch="none", commit=True)
        return True
    except Exception as e:
        logger.error(f"set_character_image_by_id failed: {e}")
        return False

def get_cast_with_images(story_id):
    return db.execute_query(
        "SELECT id, name, role, background, is_player, image FROM story_characters WHERE story_id = %s "
        "ORDER BY is_player DESC, created_at ASC", (story_id,), fetch="all") or []

def update_story_character(story_id, char_id, fields):
    """Edit template character (name/role/background). Safe: playthroughs keep copies."""
    try:
        row = db.execute_query(
            "SELECT id FROM story_characters WHERE id = %s AND story_id = %s",
            (char_id, story_id), fetch="one")
        if not row:
            return False
        allowed = {"name", "role", "background"}
        sets, params = [], []
        for k, v in (fields or {}).items():
            if k in allowed and v is not None:
                sets.append(f"{k} = %s"); params.append(str(v))
        if not sets:
            return True
        params.append(char_id)
        db.execute_query(f"UPDATE story_characters SET {', '.join(sets)} WHERE id = %s",
                         tuple(params), fetch="none", commit=True)
        return True
    except Exception as e:
        logger.error(f"update_story_character failed: {e}")
        return False

def set_story_metadata_keys(story_id, updates):
    """Merge scalar keys (starter_location, tone, ...) into stories.metadata."""
    try:
        def fn(cur):
            cur.execute("SELECT metadata FROM stories WHERE id = %s", (story_id,))
            row = cur.fetchone()
            if not row: return False
            meta = (row["metadata"] if isinstance(row["metadata"], dict) else {}) or {}
            for k, v in (updates or {}).items():
                meta[k] = v
            cur.execute("UPDATE stories SET metadata = %s, updated_at = CURRENT_TIMESTAMP WHERE id = %s",
                        (json.dumps(meta), story_id))
            return True
        return db._with_conn(fn, commit=True) is True
    except Exception as e:
        logger.error(f"set_story_metadata_keys failed: {e}")
        return False

def can_manage_story(story, user_id):
    """Owner — or anyone may adopt a legacy (pre-auth) story."""
    owner = story.get("creator_id")
    return owner == user_id or owner in (None, "", LEGACY_USER_ID)

def update_story_fields(story_id, fields):
    allowed = {"title", "genre", "premise", "cover_image", "banner_image"}
    sets, params = [], []
    for k, v in (fields or {}).items():
        if k in allowed and v is not None:
            sets.append(f"{k} = %s"); params.append(str(v))
    if not sets: return False
    sets.append("updated_at = CURRENT_TIMESTAMP")
    params.append(story_id)
    db.execute_query(f"UPDATE stories SET {', '.join(sets)} WHERE id = %s",
                     tuple(params), fetch="none", commit=True)
    return True

# ── Inventory: stacking & self-healing dedupe ──
def find_stackable_item(playthrough_id, character_id, name):
    return db.execute_query(
        "SELECT id, quantity, item_type FROM playthrough_items "
        "WHERE playthrough_id = %s AND character_id = %s AND LOWER(name) = LOWER(%s) "
        "ORDER BY created_at ASC LIMIT 1",
        (playthrough_id, character_id, name), fetch="one")

def bump_item_quantity(playthrough_id, item_id, qty=1):
    db.execute_query(
        "UPDATE playthrough_items SET quantity = LEAST(9999, quantity + %s), updated_at = CURRENT_TIMESTAMP "
        "WHERE id = %s", (int(qty), item_id), fetch="none", commit=True)
    return True

def dedupe_stackables(playthrough_id):
    """Merge duplicate stackable rows (same character + name). Idempotent & cheap."""
    try:
        def fn(cur):
            cur.execute(
                "SELECT character_id, LOWER(name) AS lname FROM playthrough_items "
                "WHERE playthrough_id = %s AND item_type IN ('consumable','material') "
                "GROUP BY character_id, LOWER(name) HAVING COUNT(*) > 1",
                (playthrough_id,))
            dups = cur.fetchall() or []
            merged = 0
            for d in dups:
                cur.execute(
                    "SELECT id, quantity FROM playthrough_items "
                    "WHERE playthrough_id = %s AND character_id = %s AND LOWER(name) = %s "
                    "ORDER BY created_at ASC",
                    (playthrough_id, d["character_id"], d["lname"]))
                rows = cur.fetchall() or []
                if len(rows) < 2: continue
                keep = rows[0]
                total = sum(int(r["quantity"]) for r in rows)
                cur.execute(
                    "UPDATE playthrough_items SET quantity = LEAST(9999, %s), updated_at = CURRENT_TIMESTAMP WHERE id = %s",
                    (total, keep["id"]))
                for r in rows[1:]:
                    cur.execute("DELETE FROM playthrough_equipment WHERE item_id = %s", (r["id"],))
                    cur.execute("DELETE FROM playthrough_items WHERE id = %s", (r["id"],))
                merged += 1
            return merged
        return db._with_conn(fn, commit=True) or 0
    except Exception as e:
        logger.error(f"dedupe_stackables failed: {e}")
        return 0

# ── Living World: nodes with state ──
def get_world_nodes_full(playthrough_id):
    try:
        return db.execute_query(
            "SELECT id, parent_id, node_type, name, metadata, status, is_alive, relationship, wealth, power, allegiance "
            "FROM world_nodes WHERE playthrough_id = %s ORDER BY created_at ASC",
            (playthrough_id,), fetch="all") or []
    except Exception:
        return db.get_world_nodes(playthrough_id)

def ensure_world_node(playthrough_id, name, kind="settlement", description=""):
    """Create-if-missing so map/world stays persistent. Never overwrites state."""
    try:
        def fn(cur):
            cur.execute(
                "SELECT id, metadata FROM world_nodes WHERE playthrough_id = %s AND LOWER(name) = LOWER(%s) LIMIT 1",
                (playthrough_id, name))
            row = cur.fetchone()
            if row:
                meta = row["metadata"] if isinstance(row["metadata"], dict) else {}
                if description and not meta.get("description"):
                    meta["description"] = description
                    cur.execute("UPDATE world_nodes SET metadata = %s, updated_at = CURRENT_TIMESTAMP WHERE id = %s",
                                (json.dumps(meta), row["id"]))
                return row["id"]
            ntype = kind if kind in VALID_NODE_TYPES else "settlement"
            new_id = str(uuid.uuid4())
            meta = {"description": description or ""}
            cur.execute(
                "INSERT INTO world_nodes (id, playthrough_id, parent_id, node_type, name, metadata, "
                "status, is_alive, relationship, wealth, power, allegiance, created_at, updated_at) "
                "VALUES (%s, %s, NULL, %s, %s, %s, 'stable', TRUE, 0, 0, 50, '', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
                (new_id, playthrough_id, ntype, name, json.dumps(meta)))
            return new_id
        return db._with_conn(fn, commit=True)
    except Exception as e:
        logger.error(f"ensure_world_node failed: {e}")
        return None

def update_world_node_state(playthrough_id, node_name, updates):
    """Upsert an entity and apply state changes. Signed values = deltas."""
    try:
        def fn(cur):
            cur.execute(
                "SELECT id, node_type, parent_id, metadata, relationship, wealth, power FROM world_nodes "
                "WHERE playthrough_id = %s AND LOWER(name) = LOWER(%s) LIMIT 1",
                (playthrough_id, node_name))
            row = cur.fetchone()

            parent_id = None
            if updates.get("parent"):
                pname = str(updates["parent"]).strip()
                cur.execute(
                    "SELECT id FROM world_nodes WHERE playthrough_id = %s AND LOWER(name) = LOWER(%s) LIMIT 1",
                    (playthrough_id, pname))
                prow = cur.fetchone()
                if prow:
                    parent_id = prow["id"]
                else:
                    pid = str(uuid.uuid4())
                    cur.execute(
                        "INSERT INTO world_nodes (id, playthrough_id, parent_id, node_type, name, metadata, "
                        "status, is_alive, relationship, wealth, power, allegiance, created_at, updated_at) "
                        "VALUES (%s, %s, NULL, 'settlement', %s, '{}', 'stable', TRUE, 0, 0, 50, '', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
                        (pid, playthrough_id, pname))
                    parent_id = pid

            created = False
            if not row:
                kind = str(updates.get("kind", "")).lower()
                if kind in ("kingdom",): kind = "region"
                if kind in ("family", "house"): kind = "faction"
                if kind in ("building", "shop", "inn", "tavern", "temple", "market"): kind = "location"
                if kind in ("city", "town", "village"): kind = "settlement"
                if kind not in VALID_NODE_TYPES:
                    kind = "npc" if (updates.get("is_alive") is not None or updates.get("relationship") is not None) else "faction"
                new_id = str(uuid.uuid4())
                meta = {"description": updates.get("description", "") or ""}
                cur.execute(
                    "INSERT INTO world_nodes (id, playthrough_id, parent_id, node_type, name, metadata, "
                    "status, is_alive, relationship, wealth, power, allegiance, created_at, updated_at) "
                    "VALUES (%s, %s, %s, %s, %s, %s, 'stable', TRUE, 0, 0, 50, '', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
                    (new_id, playthrough_id, parent_id, kind, node_name, json.dumps(meta)))
                row = {"id": new_id, "parent_id": parent_id, "relationship": 0, "wealth": 0, "power": 50, "metadata": meta}
                created = True

            sets, params = [], []
            if updates.get("status"):
                sets.append("status = %s"); params.append(str(updates["status"])[:64])
            if updates.get("allegiance"):
                sets.append("allegiance = %s"); params.append(str(updates["allegiance"])[:255])
            if "is_alive" in updates and updates["is_alive"] is not None:
                sets.append("is_alive = %s"); params.append(bool(updates["is_alive"]))
            if parent_id and not row.get("parent_id"):
                sets.append("parent_id = %s"); params.append(parent_id)
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

            if updates.get("description"):
                cur.execute("SELECT metadata FROM world_nodes WHERE id = %s", (row["id"],))
                mrow = cur.fetchone()
                meta = mrow["metadata"] if mrow and isinstance(mrow["metadata"], dict) else {}
                if not meta.get("description"):
                    meta["description"] = updates["description"]
                    cur.execute("UPDATE world_nodes SET metadata = %s, updated_at = CURRENT_TIMESTAMP WHERE id = %s",
                                (json.dumps(meta), row["id"]))
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
