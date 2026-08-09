import re
from typing import Tuple, List, Dict, Any

VALID_TIMES = {"Morning", "Afternoon", "Evening", "Night"}

def resolve_state(raw_text: str) -> Tuple[str, List[Dict[str, Any]]]:
    """
    Extracts hidden state tags from AI response and returns clean text + structured updates.
    Tags:
      [TIME_UPDATE: Day X, TimeOfDay]
      [STAT_UPDATE: CharacterName.StatName = Value] or [STAT_UPDATE: CharacterName.StatName -10]
      [LOCATION_UPDATE: LocationName]
      [ITEM_UPDATE: CharacterName + ItemName] or [ITEM_UPDATE: CharacterName - ItemName]
    """
    pattern = r'\[(TIME_UPDATE|STAT_UPDATE|LOCATION_UPDATE|ITEM_UPDATE):\s*([^\]]+)\]'
    updates = []

    def replacer(match):
        tag_type = match.group(1)
        payload = match.group(2).strip()
        parsed = _parse_payload(tag_type, payload)
        if parsed:
            updates.append(parsed)
        return ""

    clean_text = re.sub(pattern, replacer, raw_text).strip()
    return clean_text, updates

def _parse_payload(tag_type: str, payload: str) -> Dict[str, Any]:
    try:
        if tag_type == "TIME_UPDATE":
            parts = [p.strip() for p in payload.split(",")]
            if len(parts) != 2: return None
            day_str, time_str = parts
            day = int(day_str.replace("Day", "").strip())
            time_of_day = time_str.strip()
            if time_of_day not in VALID_TIMES: return None
            return {"type": "TIME_UPDATE", "day": day, "time_of_day": time_of_day}

        elif tag_type == "STAT_UPDATE":
            # Support both "= 90" and "-10" (delta)
            if "=" in payload:
                left, right = payload.split("=", 1)
                char_stat = left.strip()
                value = float(right.strip())
                is_delta = False
            else:
                # Try to extract char.stat and delta like "-10"
                m = re.match(r'([\w\s\.]+)\s+([+-]?\d+(?:\.\d+)?)$', payload)
                if not m: return None
                char_stat = m.group(1).strip()
                value = float(m.group(2))
                is_delta = True

            parts = char_stat.split(".", 1)
            if len(parts) != 2: return None
            character, stat = parts
            return {
                "type": "STAT_UPDATE",
                "character": character.strip(),
                "stat": stat.strip(),
                "value": value,
                "is_delta": is_delta
            }

        elif tag_type == "LOCATION_UPDATE":
            return {"type": "LOCATION_UPDATE", "location": payload.strip()}

        elif tag_type == "ITEM_UPDATE":
            # "CharacterName + Item Name" or "CharacterName - Item Name"
            m = re.match(r'^(.+?)\s*([+\-])\s*(.+)$', payload)
            if not m: return None
            character = m.group(1).strip()
            op = m.group(2)
            item = m.group(3).strip()
            if not character or not item: return None
            return {"type": "ITEM_UPDATE", "character": character, "add": op == "+", "item": item}

    except Exception as e:
        return None
    return None
