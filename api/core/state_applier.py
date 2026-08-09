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

def apply_state_updates(playthrough_id: str, updates: list) -> list:
    applied = []
    for update in updates:
        try:
            utype = update.get("type")
            if utype == "TIME_UPDATE":
                db.update_playthrough_time(playthrough_id, update["day"], update["time_of_day"])
                applied.append(update)

            elif utype == "STAT_UPDATE":
                char_name = update["character"]
                stat_name = update["stat"]
                new_value = update["value"]
                is_delta = update.get("is_delta", False)

                if is_delta:
                    chars = db.get_playthrough_characters(playthrough_id)
                    current = None
                    for c in chars:
                        if c["character_name"].lower() == char_name.lower():
                            meta = c.get("metadata") or {}
                            stats = meta.get("stats", {})
                            current = stats.get(stat_name, 100)
                            break
                    if current is not None:
                        new_value = float(current) + float(new_value)

                if db.update_playthrough_character_stat(playthrough_id, char_name, stat_name, new_value, max_value=999):
                    applied.append(update)

            elif utype == "LOCATION_UPDATE":
                # ADDITIVE: Uses the new upsert method to track locations in the new table
                db.upsert_playthrough_location(playthrough_id, update["location"])
                applied.append(update)

        except Exception as e:
            logger.error(f"Failed to apply state update {update}: {e}")
            continue

    return applied
