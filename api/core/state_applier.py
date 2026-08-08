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

def apply_state_updates(story_id: str, updates: list) -> list:
    """
    Applies parsed state updates to the database.
    Returns a list of successfully applied updates.
    """
    applied = []
    for update in updates:
        try:
            utype = update.get("type")
            if utype == "TIME_UPDATE":
                db.update_story_time(story_id, update["day"], update["time_of_day"])
                applied.append(update)

            elif utype == "STAT_UPDATE":
                char_name = update["character"]
                stat_name = update["stat"]
                new_value = update["value"]
                is_delta = update.get("is_delta", False)

                if is_delta:
                    # Fetch current stat value and apply delta
                    chars = db.get_story_characters(story_id)
                    current = None
                    for c in chars:
                        if c["name"].lower() == char_name.lower():
                            meta = c.get("metadata") or {}
                            stats = meta.get("stats", {})
                            current = stats.get(stat_name, 100)
                            break
                    if current is not None:
                        new_value = float(current) + float(new_value)

                success = db.update_character_stat(story_id, char_name, stat_name, new_value, max_value=999)
                if success:
                    applied.append(update)

            elif utype == "LOCATION_UPDATE":
                db.update_story_location(story_id, update["location"])
                applied.append(update)

        except Exception as e:
            logger.error(f"Failed to apply state update {update}: {e}")
            continue

    return applied
