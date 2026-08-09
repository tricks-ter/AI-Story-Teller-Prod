import re
from typing import Tuple, List, Dict, Any

VALID_TIMES = {"Morning", "Afternoon", "Evening", "Night"}

ATTR_KEY_RE = re.compile(
    r'(?:type|slot|rarity|level|weight|desc|description|use_effect|bonus\.[A-Za-z0-9_]+)\s*=',
    re.IGNORECASE)

def split_name_attrs(main_part: str) -> Tuple[str, str]:
    m = re.search(
        r'[,|]\s*(?=(?:type|slot|rarity|level|weight|desc|description|use_effect|bonus\.[A-Za-z0-9_]+)\s*=)',
        main_part, re.IGNORECASE)
    if not m:
        return main_part.strip(), ""
    return main_part[:m.start()].strip(), main_part[m.start():].lstrip(",| ").strip()

def clean_entity_name(name: str, max_len: int = 60) -> str:
    s = re.sub(r'\s+', ' ', name or "").strip()
    if ATTR_KEY_RE.search(s):
        s = ATTR_KEY_RE.split(s, 1)[0]
    s = s.strip(" ,;|-")
    if not s and name:
        s = name[:max_len].strip()
    return s[:max_len].strip()

def resolve_state(raw_text: str) -> Tuple[str, List[Dict[str, Any]]]:
    pattern = r'\[(TIME_UPDATE|STAT_UPDATE|LOCATION_UPDATE|ITEM_UPDATE|ABILITY_UPDATE|BAG_UPDATE|CURRENCY_UPDATE|SAGA_END):\s*([^\]]+)\]'
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
        k = k.strip().lower(); v = v.strip()
        if k.startswith("bonus."):
            try:
                bonuses[k.split(".", 1)[1].strip()] = float(v)
            except Exception:
                pass
        elif k in ("desc", "description"):
            out["description"] = v
        elif k == "use_effect":
            out["use_effect"] = v
        else:
            out[k] = v
    typed: Dict[str, Any] = {}
    if "type" in out: typed["type"] = out["type"].lower()
    if "slot" in out: typed["slot"] = out["slot"].lower()
    if "rarity" in out: typed["rarity"] = out["rarity"].lower()
    if "description" in out: typed["description"] = out["description"]
    if "use_effect" in out: typed["use_effect"] = out["use_effect"]
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
            return {"type": "STAT_UPDATE", "character": character.strip(), "stat": stat.strip(), "value": value, "is_delta": is_delta}

        elif tag_type == "LOCATION_UPDATE":
            main_part = payload
            attrs = {}
            if "|" in payload:
                main_part, attr_part = payload.split("|", 1)
                attrs = _parse_attrs(attr_part)
            name = clean_entity_name(main_part, max_len=80)
            if not name: return None
            return {"type": "LOCATION_UPDATE", "location": name, "description": attrs.get("description", "")}

        elif tag_type == "ITEM_UPDATE":
            main_part = payload
            attrs = {}
            if "|" in payload:
                main_part, attr_part = payload.split("|", 1)
                attrs = _parse_attrs(attr_part)
            name_part, tail = split_name_attrs(main_part)
            if tail:
                for k, v in _parse_attrs(tail).items():
                    attrs.setdefault(k, v)
            m = re.match(r'^(.+?)\s*([+-])\s*(.+)$', name_part.strip())
            if not m: return None
            character = clean_entity_name(m.group(1), max_len=60); op = m.group(2)
            item = clean_entity_name(m.group(3))
            if not character or not item: return None
            return {"type": "ITEM_UPDATE", "character": character, "add": op == "+", "item": item, "attrs": attrs}

        elif tag_type == "ABILITY_UPDATE":
            main_part = payload
            attrs = {}
            if "|" in payload:
                main_part, attr_part = payload.split("|", 1)
                attrs = _parse_attrs(attr_part)
            name_part, tail = split_name_attrs(main_part)
            if tail:
                for k, v in _parse_attrs(tail).items():
                    attrs.setdefault(k, v)
            m = re.match(r'^(.+?)\s*([+-])\s*(.+)$', name_part.strip())
            if not m: return None
            character = clean_entity_name(m.group(1), max_len=60); op = m.group(2)
            ability = clean_entity_name(m.group(3))
            if not character or not ability: return None
            return {"type": "ABILITY_UPDATE", "character": character, "add": op == "+", "ability": ability, "description": attrs.get("description", "")}

        elif tag_type == "BAG_UPDATE":
            m = re.match(r'^(.+?)\s+(?:level|=)\s*(\d+)$', payload, re.IGNORECASE)
            if not m: return None
            character = m.group(1).strip(); level = int(m.group(2))
            if not character: return None
            return {"type": "BAG_UPDATE", "character": character, "level": level}

        elif tag_type == "CURRENCY_UPDATE":
            m = re.match(r'^(.+?)\s*([+-])\s*(\d+)$', payload.strip())
            if not m: return None
            character = m.group(1).strip(); op = m.group(2); amount = int(m.group(3))
            return {"type": "CURRENCY_UPDATE", "character": character, "add": op == "+", "amount": amount}

        elif tag_type == "SAGA_END":
            return {"type": "SAGA_END"}

    except Exception as e:
        return None
    return None
