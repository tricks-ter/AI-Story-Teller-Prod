"""
Phase 5.5 — Pulse State-Sync & Rolling Memory.

Three layered, additive safety nets that run after every narration turn:
  1. sanitize_existing_items(): deterministic repair of legacy malformed item
     names (containing key= fragments) and conversion of soul-ring items into
     abilities (rings are powers, never backpack loot).
  2. pulse_reconcile(): one cheap glm-4.5-flash ("Pulse") call that re-reads the
     last turn and emits the structured deltas the narrator model forgot
     (time, location, items, abilities, stat deltas) PLUS a rolling story
     summary and a one-line CURRENT SITUATION anchor (stored in playthroughs.metadata).
  3. fallback_clock(): deterministic beat-based clock advance so Day/Time never
     freezes even when both tags and Pulse stay silent.

Everything here is best-effort: failures are logged and swallowed so narration
can never break (Rule 4). No schema changes — reuses JSONB metadata (Rule 8).
"""
import os
import sys
import re
import json
import logging

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(BASE_DIR)
for _p in (PARENT_DIR, BASE_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from database import db
from core.state_resolver import VALID_TIMES, clean_entity_name, split_name_attrs
from core.state_applier import apply_state_updates, _resolve_character_id
from core.resilience import call_with_retry

logger = logging.getLogger(__name__)

PULSE_MODEL = os.getenv("PULSE_MODEL", "glm-4.5-flash")
TIME_ORDER = ["Morning", "Afternoon", "Evening", "Night"]
SOUL_RING_RE = re.compile(r'(soul|spirit)\s*ring', re.IGNORECASE)


def next_tick(day: int, time_of_day: str):
    """Pure helper: one deterministic clock step. Testable without DB."""
    idx = TIME_ORDER.index(time_of_day) if time_of_day in TIME_ORDER else 0
    if idx == len(TIME_ORDER) - 1:
        return int(day) + 1, TIME_ORDER[0]
    return int(day), TIME_ORDER[idx + 1]


def _patch_playthrough_meta(playthrough_id: str, patch: dict):
    if not patch:
        return
    db.execute_query(
        "UPDATE playthroughs SET metadata = COALESCE(metadata, '{}') || %s::jsonb, "
        "updated_at = CURRENT_TIMESTAMP WHERE id = %s",
        (json.dumps(patch), playthrough_id), fetch="none", commit=True)


def sanitize_existing_items(playthrough_id: str) -> int:
    """Repair rows created before name-sanitization existed. Returns rename count."""
    renamed = 0
    try:
        for it in db.list_playthrough_items(playthrough_id):
            name = it.get("name") or ""
            if "=" in name:
                fixed = clean_entity_name(split_name_attrs(name)[0]) or name[:60]
                if fixed and fixed != name:
                    db.execute_query(
                        "UPDATE playthrough_items SET name = %s, updated_at = CURRENT_TIMESTAMP "
                        "WHERE id = %s AND playthrough_id = %s",
                        (fixed, it["id"], playthrough_id), fetch="none", commit=True)
                    renamed += 1

        chars = db.get_playthrough_characters(playthrough_id)
        for it in db.list_playthrough_items(playthrough_id):
            iname = it.get("name") or ""
            if not SOUL_RING_RE.search(iname):
                continue
            char_id = it["character_id"]
            meta = it.get("metadata") if isinstance(it.get("metadata"), dict) else {}
            desc = (meta or {}).get("description", "") or "An absorbed soul ring humming with borrowed power."
            db.update_playthrough_character_ability(playthrough_id, char_id, clean_entity_name(iname), True, desc)
            db.execute_query("DELETE FROM playthrough_equipment WHERE item_id = %s", (it["id"],), fetch="none", commit=True)
            db.execute_query("DELETE FROM playthrough_items WHERE id = %s AND playthrough_id = %s",
                             (it["id"], playthrough_id), fetch="none", commit=True)
            for c in chars:
                cmeta = c.get("metadata") if isinstance(c.get("metadata"), dict) else {}
                inv = (cmeta or {}).get("inventory", [])
                if isinstance(inv, list) and any(SOUL_RING_RE.search(str(i)) for i in inv):
                    cmeta["inventory"] = [i for i in inv if not SOUL_RING_RE.search(str(i))]
                    db.execute_query("UPDATE playthrough_characters SET metadata = %s WHERE id = %s",
                                     (json.dumps(cmeta), c["id"]), fetch="none", commit=True)
    except Exception as e:
        logger.error(f"sanitize_existing_items failed: {e}")
    return renamed


def fallback_clock(playthrough_id: str, time_already_moved: bool) -> bool:
    """Advance the clock deterministically when neither tags nor Pulse moved it.
    One period per 2 quiet turns; Night rolls to the next Day's Morning."""
    if time_already_moved:
        return False
    pt = db.get_playthrough(playthrough_id)
    if not pt:
        return False
    meta = pt.get("metadata") if isinstance(pt.get("metadata"), dict) else {}
    beat = int((meta or {}).get("time_beat", 0)) + 1
    if beat < 2:
        _patch_playthrough_meta(playthrough_id, {"time_beat": beat})
        return False
    day, tod = next_tick(int(pt["current_day"]), pt["time_of_day"])
    db.update_playthrough_time(playthrough_id, day, tod)
    _patch_playthrough_meta(playthrough_id, {"time_beat": 0})
    return True


def _parse_json_lenient(text: str):
    if not text:
        return None
    t = text.strip()
    t = re.sub(r'^```(?:json)?', '', t).strip()
    t = re.sub(r'```$', '', t).strip()
    start, end = t.find('{'), t.rfind('}')
    if start < 0 or end <= start:
        return None
    try:
        return json.loads(t[start:end + 1])
    except Exception:
        return None


def _build_pulse_prompt(pt, chars, carried_names, ability_names, equipped_names,
                        user_action, narration):
    meta = pt.get("metadata") if isinstance(pt.get("metadata"), dict) else {}
    return f"""You are InkMind Pulse, a world-state bookkeeper for an RPG. Read the last turn and output STRICT JSON only (no prose, no markdown).

CURRENT STATE: Day {pt['current_day']}, {pt['time_of_day']}. Location: {meta.get('current_location', 'unknown')}.
Carried items: {carried_names or 'none'}. Equipped: {equipped_names or 'none'}. Abilities: {ability_names or 'none'}.
Previous summary: {meta.get('story_summary', '') or '(none yet)'}

PLAYER ACTION: {user_action}
NARRATION: {narration[:3000]}

Rules:
- time_of_day in {sorted(VALID_TIMES)}; advance ~one period per scene; sleep/travel may jump more; day only increases.
- location = where the character physically is NOW (short name).
- Powers, soul rings, skills, knowledge => abilities_add (NEVER items). Physical loot => items_add. Consumed/lost items => items_remove using the EXACT carried name.
- hp_delta/mp_delta are small integers (-30..30), 0 if unchanged.
- summary = merge Previous summary with this turn into <=3 sentences of long-term plot.
- situation = ONE line describing the exact current moment (place + immediate tension).

JSON schema:
{{"day": 1, "time_of_day": "Morning", "location": "", "location_desc": "", "items_add": [{{"name": "", "type": "material", "slot": "", "rarity": "common", "weight": 1, "desc": ""}}], "items_remove": [], "abilities_add": [{{"name": "", "desc": ""}}], "hp_delta": 0, "mp_delta": 0, "summary": "", "situation": ""}}"""


def pulse_reconcile(playthrough_id: str, user_action: str, narration: str):
    """One cheap Pulse call; returns parsed dict or None. Raises on upstream failure (caller catches)."""
    api_key = os.getenv("ZAI_API_KEY", "")
    if not api_key:
        return None
    pt = db.get_playthrough(playthrough_id)
    if not pt:
        return None
    chars = db.get_playthrough_characters(playthrough_id)
    carried, equipped, abilities = [], [], []
    for c in chars:
        carried += [i["name"] for i in db.list_carried_items_for_character(c["id"])]
        equipped += [e["item_name"] for e in db.list_equipment_for_character(c["id"])]
        cmeta = c.get("metadata") if isinstance(c.get("metadata"), dict) else {}
        abilities += [a.get("name", "") for a in (cmeta or {}).get("abilities", []) if isinstance(a, dict)]
    prompt = _build_pulse_prompt(pt, chars, carried, abilities, equipped, user_action, narration)

    from zai import ZaiClient
    client = ZaiClient(api_key=api_key)
    resp = call_with_retry(
        lambda: client.chat.completions.create(
            model=PULSE_MODEL,
            messages=[{"role": "user", "content": prompt}],
            stream=False, max_tokens=600, temperature=0.2,
            thinking={"type": "disabled"}),
        max_attempts=2, label="pulse")
    return _parse_json_lenient(getattr(resp.choices[0].message, "content", "") or "")


def _updates_from_pulse(playthrough_id: str, data: dict, player_name: str, carried_names: list):
    ups = []
    try:
        day = int(data.get("day", 0))
        tod = str(data.get("time_of_day", "")).strip()
        if day >= 1 and tod in VALID_TIMES:
            ups.append({"type": "TIME_UPDATE", "day": day, "time_of_day": tod})
    except Exception:
        pass
    loc = clean_entity_name(str(data.get("location", "") or ""), max_len=80)
    if loc:
        ups.append({"type": "LOCATION_UPDATE", "location": loc,
                    "description": str(data.get("location_desc", "") or "")[:200]})
    for a in data.get("abilities_add", []) or []:
        if isinstance(a, dict) and a.get("name"):
            ups.append({"type": "ABILITY_UPDATE", "character": player_name, "add": True,
                        "ability": clean_entity_name(str(a["name"])),
                        "description": str(a.get("desc", "") or "")[:200]})
    for it in data.get("items_add", []) or []:
        if not isinstance(it, dict) or not it.get("name"):
            continue
        name = clean_entity_name(str(it["name"]))
        if not name:
            continue
        if SOUL_RING_RE.search(name):
            ups.append({"type": "ABILITY_UPDATE", "character": player_name, "add": True,
                        "name and ability": None, "ability": name,
                        "description": str(it.get("desc", "") or "")[:200]})
            continue
        attrs = {}
        if str(it.get("type", "")).lower() in ("weapon", "armor", "accessory", "consumable", "material", "quest"):
            attrs["type"] = str(it["type"]).lower()
        if str(it.get("slot", "")).lower() in ("main_hand", "off_hand", "head", "body", "ring", "amulet", "trinket"):
            attrs["slot"] = str(it["slot"]).lower()
        if str(it.get("rarity", "")).lower() in ("common", "uncommon", "rare", "epic", "legendary"):
            attrs["rarity"] = str(it["rarity"]).lower()
        try:
            attrs["weight"] = max(0, min(99, int(float(it.get("weight", 1)))))
        except Exception:
            pass
        if it.get("desc"):
            attrs["description"] = str(it["desc"])[:200]
        ups.append({"type": "ITEM_UPDATE", "character": player_name, "add": True, "item": name, "attrs": attrs})
    carried_lower = {n.lower(): n for n in carried_names}
    for nm in data.get("items_remove", []) or []:
        exact = carried_lower.get(str(nm).strip().lower())
        if exact:
            ups.append({"type": "ITEM_UPDATE", "character": player_name, "add": False, "item": exact, "attrs": {}})
    for stat, key in (("Health", "hp_delta"), ("Mana", "mp_delta")):
        try:
            d = float(data.get(key, 0) or 0)
            if d:
                ups.append({"type": "STAT_UPDATE", "character": player_name, "stat": stat,
                            "value": max(-30, min(30, d)), "is_delta": True})
        except Exception:
            pass
    return ups


def run_state_sync(playthrough_id: str, user_action: str, narration: str,
                   time_already_moved: bool = False) -> dict:
    """Orchestrates repair + Pulse reconciliation + clock fallback. Never raises."""
    out = {"synced": False, "time_moved": bool(time_already_moved), "applied": 0, "rejected": 0}
    try:
        sanitize_existing_items(playthrough_id)
    except Exception as e:
        logger.error(f"sync sanitize skipped: {e}")

    data = None
    try:
        data = pulse_reconcile(playthrough_id, user_action, narration)
    except Exception as e:
        logger.error(f"pulse reconcile skipped: {e}")

    if isinstance(data, dict):
        try:
            chars = db.get_playthrough_characters(playthrough_id)
            player = next((c for c in chars if c["is_player"]), None) or (chars[0] if chars else None)
            player_name = player["character_name"] if player else "Player"
            carried_names = [i["name"] for i in db.list_carried_items_for_character(player["id"])] if player else []
            ups = _updates_from_pulse(playthrough_id, data, player_name, carried_names)
            if ups:
                res = apply_state_updates(playthrough_id, ups)
                out["applied"] = len(res.get("applied", []))
                out["rejected"] = len(res.get("rejected", []))
                if any(u.get("type") == "TIME_UPDATE" for u in res.get("applied", [])):
                    out["time_moved"] = True
                    _patch_playthrough_meta(playthrough_id, {"time_beat": 0})
            patch = {}
            summary = str(data.get("summary", "") or "").strip()
            situation = str(data.get("situation", "") or "").strip()
            if summary:
                patch["story_summary"] = summary[:2000]
            if situation:
                patch["current_situation"] = situation[:300]
            if patch:
                _patch_playthrough_meta(playthrough_id, patch)
            out["synced"] = True
        except Exception as e:
            logger.error(f"pulse apply skipped: {e}")

    try:
        if fallback_clock(playthrough_id, out["time_moved"]):
            out["time_moved"] = True
    except Exception as e:
        logger.error(f"fallback clock skipped: {e}")
    return out
