import os
import sys
import logging

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(BASE_DIR)
for _p in (PARENT_DIR, BASE_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from database import db
import db_ext

logger = logging.getLogger(__name__)

STACKABLE_TYPES = {"consumable", "material"}

def apply_state_updates(playthrough_id: str, updates: list) -> dict:
    applied = []
    rejected = []
    for update in updates:
        try:
            utype = update.get("type")
            if utype == "TIME_UPDATE":
                db.update_playthrough_time(playthrough_id, max(1, int(update["day"])), update["time_of_day"])
                applied.append(update)

            elif utype == "STAT_UPDATE":
                char_name = update["character"]
                stat_name = update["stat"]
                new_value = update["value"]
                # CRITICAL: Always treat as delta if is_delta is True
                if update.get("is_delta", False):
                    chars = db.get_playthrough_characters(playthrough_id)
                    current = None
                    for c in chars:
                        if c["character_name"].lower() == char_name.lower():
                            meta = c.get("metadata") or {}
                            current = (meta.get("stats", {})).get(stat_name, 100)
                            break
                    if current is not None:
                        new_value = float(current) + float(new_value)
                if db.update_playthrough_character_stat(playthrough_id, char_name, stat_name, new_value, max_value=999):
                    applied.append(update)

            elif utype == "LOCATION_UPDATE":
                if db.upsert_playthrough_location(playthrough_id, update["location"], update.get("description", "")):
                    applied.append(update)
                    # Persist every discovered place in the world graph
                    db_ext.ensure_world_node(playthrough_id, update["location"], kind="settlement",
                                             description=update.get("description", ""))
                else:
                    rejected.append({**update, "reason": "location_error"})

            elif utype == "ITEM_UPDATE":
                char_id = _resolve_character_id(playthrough_id, update["character"])
                if not char_id:
                    rejected.append({**update, "reason": "character_not_found"}); continue
                if update.get("add", True):
                    attrs = update.get("attrs") or {}
                    new_type = str(attrs.get("type") or "").lower()
                    # DUPLICATE FIX: if the character already carries this stackable item, bump quantity.
                    existing = db_ext.find_stackable_item(playthrough_id, char_id, update["item"])
                    if existing and existing["item_type"] in STACKABLE_TYPES and new_type in ("", "consumable", "material"):
                        db_ext.bump_item_quantity(playthrough_id, existing["id"], 1)
                        applied.append(update)
                        continue
                    res = db.grant_playthrough_item(playthrough_id, char_id, update["item"], attrs)
                    if res.get("ok"): applied.append(update)
                    else: rejected.append({**update, "reason": res.get("reason", "rejected")})
                else:
                    if db.consume_playthrough_item(playthrough_id, char_id, update["item"]): applied.append(update)
                    else: rejected.append({**update, "reason": "item_not_found"})

            elif utype == "ABILITY_UPDATE":
                char_id = _resolve_character_id(playthrough_id, update["character"])
                if not char_id:
                    rejected.append({**update, "reason": "character_not_found"}); continue
                if db.update_playthrough_character_ability(playthrough_id, char_id, update["ability"], bool(update.get("add", True)), update.get("description", "")):
                    applied.append(update)
                else:
                    rejected.append({**update, "reason": "character_not_found"})

            elif utype == "BAG_UPDATE":
                char_id = _resolve_character_id(playthrough_id, update["character"])
                if not char_id:
                    rejected.append({**update, "reason": "character_not_found"})
                elif db.set_playthrough_backpack_level(playthrough_id, char_id, update["level"]):
                    applied.append(update)
                else:
                    rejected.append({**update, "reason": "backpack_error"})

            elif utype == "WORLD_STATE_UPDATE":
                res = db_ext.update_world_node_state(playthrough_id, update["name"], update)
                if res.get("ok"):
                    applied.append(update)
                else:
                    rejected.append({**update, "reason": res.get("reason", "world_error")})

            elif utype == "WORLD_EVENT":
                pt = db.get_playthrough(playthrough_id)
                day = pt["current_day"] if pt else 1
                if db_ext.record_world_event(playthrough_id, update["name"], update.get("event_type", "event"), update.get("description", ""), day):
                    applied.append(update)
                else:
                    rejected.append({**update, "reason": "event_error"})

            elif utype == "SAGA_END":
                db.complete_playthrough(playthrough_id)
                applied.append(update)

        except Exception as e:
            logger.error(f"Failed to apply state update {update}: {e}")
            rejected.append({**update, "reason": "internal_error"})
            continue

    return {"applied": applied, "rejected": rejected}

def _resolve_character_id(playthrough_id: str, character_name: str):
    for c in db.get_playthrough_characters(playthrough_id):
        if c["character_name"].lower() == character_name.lower():
            return c["id"]
    return None
