import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(BASE_DIR)
for _p in (PARENT_DIR, BASE_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from database import db


def _recent_messages(playthrough_id: str, limit: int = 15):
    rows = db.execute_query(
        "SELECT id, role, content, message_type, created_at FROM story_messages "
        "WHERE playthrough_id = %s ORDER BY id DESC LIMIT %s",
        (playthrough_id, int(limit)), fetch="all") or []
    return list(reversed(rows))


class PromptAssembler:
    def __init__(self, playthrough_id: str):
        self.playthrough_id = playthrough_id

    def assemble_full_prompt(self, user_action: str) -> str:
        pt = db.get_playthrough(self.playthrough_id)
        if not pt:
            return "You are a helpful assistant."
        story = db.get_story(pt["story_id"])
        if not story:
            return "You are a helpful assistant."

        characters = db.get_playthrough_characters(self.playthrough_id)
        messages = _recent_messages(self.playthrough_id, limit=15)
        notes = db.get_story_notes(story["id"], active_only=True)

        system = f"""[SYSTEM INSTRUCTIONS]
You are a master storyteller and interactive fiction engine for a {story['genre']} RPG.
Write in 2nd-person present tense ("You draw your sword...").
Hidden state tags (own line):
  [TIME_UPDATE: Day X, TimeOfDay]
  [STAT_UPDATE: CharacterName.StatName = NewValue] / [STAT_UPDATE: CharacterName.StatName -10]
  [LOCATION_UPDATE: LocationName | desc=One-sentence chronicle of the place]
  [ITEM_UPDATE: CharacterName + ItemName | type=weapon, slot=main_hand, rarity=rare, level=4, weight=3, bonus.Health=10, desc=Short description, use_effect=What happens when used]
  [ITEM_UPDATE: CharacterName - ItemName]
  [ABILITY_UPDATE: CharacterName + Ability Name | desc=What it does]
  [BAG_UPDATE: CharacterName level N]
  [CURRENCY_UPDATE: CharacterName + N] / [CURRENCY_UPDATE: CharacterName - N]
  [SAGA_END] (ONLY when the player explicitly ends the story or a true ending is reached)
Item types: weapon, armor, accessory, consumable, material, quest.
Slots: main_hand, off_hand, head, body, ring, amulet, trinket.
Rarities: common, uncommon, rare, epic, legendary.

[STATE TAG RULES - CRITICAL]
- Physical objects -> ITEM_UPDATE. Powers/skills/soul rings/spirit rings/knowledge -> ABILITY_UPDATE (never in backpack).
- ALWAYS emit [LOCATION_UPDATE] (with desc=) when a location is first described, when the party moves, or when the player asks where they are.
- Always include short desc= and use_effect= for new items. Use_effect explains what happens if the item is used/consumed.
- Names must NOT contain "key=value" fragments; attributes go ONLY after the | separator.
- Respect remaining backpack capacity.
- Currency (coins, gold, credits) -> CURRENCY_UPDATE.

[TIME RULES - CRITICAL]
- Emit [TIME_UPDATE] on EVERY response. One scene ≈ one period: Morning → Afternoon → Evening → Night.

[CONTINUITY RULES - CRITICAL]
- NEVER re-tell, recap or repeat a scene that already happened. Start every response from CURRENT SITUATION below.
- If the player asks a question (where am I? what now?), answer it directly and briefly in-world, then move the scene forward.

[PLAYER AGENCY RULES - CRITICAL]
- NEVER perform the player's chosen action for them, and NEVER describe its outcome.
- Stop at the moment of decision, or just as the action begins.

[STYLE RULES - CRITICAL]
- CLEAR, SIMPLE, EASY-TO-IMAGINE language. What can be SEEN, HEARD, FELT.
- Dialogue in double quotes; narration without quotes.
- At most 1-2 new elements per turn. 2-4 short paragraphs.
"""

        world = f"""[WORLD STATE]
Story: {story['title']}
Premise: {story['premise']}
Current Day: {pt['current_day']}
Time of Day: {pt['time_of_day']}
"""
        meta = pt.get("metadata") or {}
        if meta.get("current_location"):
            world += f"Current Location: {meta['current_location']}\n"

        if meta.get("story_summary"):
            world += f"\n[STORY SO FAR]\n{meta['story_summary']}\n"
        world += f"\n[CURRENT SITUATION]\n{meta.get('current_situation', '') or 'The story is just beginning.'}\n"

        world += "\nActive Characters:\n"
        for c in characters:
            cmeta = c.get("metadata") or {}
            stats = cmeta.get("stats", {})
            world += f"- {c['character_name']} ({c['role']}): Background: {c['background']}. Stats: {stats}\n"

            abilities = cmeta.get("abilities", [])
            if isinstance(abilities, list) and abilities:
                world += "  Abilities: " + ", ".join(
                    a.get("name", "?") for a in abilities if isinstance(a, dict)) + "\n"

            carried = db.list_carried_items_for_character(c["id"])
            legacy_inv = cmeta.get("inventory", [])
            if carried:
                world += "  Carried: " + ", ".join(
                    f"{i['name']} ×{i['quantity']}" if i["quantity"] > 1 else i["name"] for i in carried) + "\n"
            elif isinstance(legacy_inv, list) and legacy_inv:
                world += "  Carried: " + ", ".join(str(x) for x in legacy_inv) + "\n"

            equipped = db.list_equipment_for_character(c["id"])
            if equipped:
                world += "  Equipped: " + ", ".join(
                    f"{e['item_name']} ({e['slot']}, lv{e['item_level']})" for e in equipped) + "\n"

            bp = db.get_backpack_for_character(c["id"])
            if bp:
                used = db.backpack_used_capacity(c["id"])
                world += f"  Backpack: Level {bp['level']}, load {used}/{5 + bp['level'] * 5}\n"

        known = db.get_playthrough_map(self.playthrough_id)
        if known:
            world += "\nKnown Locations (journey so far): " + ", ".join(l["name"] for l in known) + "\n"

        context = "\n[RECENT STORY CONTEXT]\n"
        for m in messages:
            role = "Player" if m["role"] == "user" else "Narrator"
            context += f"{role}: {m['content']}\n"

        director = ""
        if notes:
            director = "\n[DIRECTOR'S NOTES - High Priority Overrides]\n"
            for n in notes:
                director += f"- {n['content']}\n"

        action = f"\n[PLAYER'S CURRENT ACTION]\n{user_action}\n\nRespond with clear, immersive narrative prose. Stop before the outcome."

        return system + world + context + director + action
