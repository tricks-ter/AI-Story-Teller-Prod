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
      [ITEM_UPDATE: CharacterName + ItemName | type=weapon, slot=main_hand, rarity=rare, level=4, weight=3, bonus.Health=10]
      [ITEM_UPDATE: CharacterName - ItemName]
      [BAG_UPDATE: CharacterName level N]
    """
    pattern = r'\[(TIME_UPDATE|STAT_UPDATE|LOCATION_UPDATE|ITEM_UPDATE|BAG_UPDATE):\s*([^\]]+)\]'
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

def _parse_attrs(raw: str) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    bonuses: Dict[str, float] = {}
    for part in raw.split(","):
        part = part.strip()
        if not part or "=" not in part:
            continue
        k, v = part.split("=", 1)
        k = k.strip(); v = v.strip()
        if k.startswith("bonus."):
            try:
                bonuses[k.split(".", 1)[1].strip()] = float(v)
            except Exception:
                pass
        else:
            out[k.lower()] = v
    typed: Dict[str, Any] = {}
    if "type" in out: typed["type"] = out["type"].lower()
    if "slot" in out: typed["slot"] = out["slot"].lower()
    if "rarity" in out: typed["rarity"] = out["rarity"].lower()
    try:
        if "level" in out: typed["level"] = int(float(out["level"]))
    except Exception:
        pass
    try:
        if "weight" in out: typed["weight"] = int(float(out["weight"]))
    except Exception:
        pass
    if bonuses:
        typed["bonuses"] = bonuses
    return typed

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
            if "=" in payload:
                left, right = payload.split("=", 1)
                char_stat = left.strip()
                value = float(right.strip())
                is_delta = False
            else:
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
            main_part = payload
            attrs = {}
            if "|" in payload:
                main_part, attr_part = payload.split("|", 1)
                attrs = _parse_attrs(attr_part)
            m = re.match(r'^(.+?)\s*([+\-])\s*(.+)$', main_part.strip())
            if not m: return None
            character = m.group(1).strip()
            op = m.group(2)
            item = m.group(3).strip()
            if not character or not item: return None
            return {"type": "ITEM_UPDATE", "character": character, "add": op == "+", "item": item, "attrs": attrs}

        elif tag_type == "BAG_UPDATE":
            m = re.match(r'^(.+?)\s+(?:level|=)\s*(\d+)$', payload, re.IGNORECASE)
            if not m: return None
            character = m.group(1).strip()
            level = int(m.group(2))
            if not character: return None
            return {"type": "BAG_UPDATE", "character": character, "level": level}

    except Exception as e:
        return None
    return None
