import os
import sys
import logging

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(BASE_DIR)
for _p in (PARENT_DIR, BASE_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from database import db

logger = logging.getLogger(__name__)

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
                is_delta = update.get("is_delta", False)
                
                chars = db.get_playthrough_characters(playthrough_id)
                current = 100.0
                for c in chars:
                    if c["character_name"].lower() == char_name.lower():
                        meta = c.get("metadata") or {}
                        current = float((meta.get("stats", {})).get(stat_name, 100))
                        break
                
                target = float(current) + float(new_value) if is_delta else float(new_value)
                clamped = max(0.0, min(float(999), target))
                
                if db.update_playthrough_character_stat(playthrough_id, char_name, stat_name, clamped, max_value=999):
                    applied.append({**update, "value": clamped, "is_delta": False})

            elif utype == "LOCATION_UPDATE":
                if db.upsert_playthrough_location(playthrough_id, update["location"], update.get("description", "")):
                    applied.append(update)
                else:
                    rejected.append({**update, "reason": "location_error"})

            elif utype == "ITEM_UPDATE":
                char_id = _resolve_character_id(playthrough_id, update["character"])
                if not char_id:
                    rejected.append({**update, "reason": "character_not_found"}); continue
                if update.get("add", True):
                    res = db.grant_playthrough_item(playthrough_id, char_id, update["item"], update.get("attrs") or {})
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

            elif utype == "CURRENCY_UPDATE":
                new_val = db.update_playthrough_currency(playthrough_id, update["amount"], is_delta=update.get("add", True))
                applied.append({"type": "CURRENCY_UPDATE", "amount": new_val, "is_delta": False})

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
