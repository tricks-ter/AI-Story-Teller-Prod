import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(BASE_DIR)
for _p in (PARENT_DIR, BASE_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from database import db

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
        messages = db.get_playthrough_messages(self.playthrough_id, limit=15)
        notes = db.get_story_notes(story["id"], active_only=True)

        system = f"""[SYSTEM INSTRUCTIONS]
You are a master storyteller and interactive fiction engine for a {story['genre']} RPG.
Write in 2nd-person present tense ("You draw your sword...").
You may use hidden state tags on their own line to update world state:
  [TIME_UPDATE: Day X, TimeOfDay]  (Morning/Afternoon/Evening/Night)
  [STAT_UPDATE: CharacterName.StatName = NewValue]
  [STAT_UPDATE: CharacterName.StatName -10]
  [LOCATION_UPDATE: NewLocationName]
  [ITEM_UPDATE: CharacterName + ItemName | type=weapon, slot=main_hand, rarity=rare, level=4, weight=3, bonus.Health=10]
  [ITEM_UPDATE: CharacterName - ItemName]  (consume/remove; quantity decreases)
  [BAG_UPDATE: CharacterName level N]  (backpack upgrade; more carry capacity)
Item types: weapon, armor, accessory, consumable, material, quest.
Slots: main_hand, off_hand, head, body, ring, amulet, trinket.
Rarities: common, uncommon, rare, epic, legendary.
Respect the player's remaining backpack capacity — do not grant loot that won't fit.
Use tags sparingly, only when the narrative justifies it.

[PLAYER AGENCY RULES - CRITICAL]
- NEVER perform the player's chosen action for them, and NEVER describe its outcome.
- Stop your response at the moment of decision, or just as the action begins.
- End with the situation, a threat, a revelation, or a question — leave the RESULT to the player's next input.
- Do not invent new player decisions, movements, attacks, or dialogue beyond what the player typed.
- The player is the only author of their character's choices.

[STYLE RULES - CRITICAL]
- Write in CLEAR, SIMPLE, EASY-TO-IMAGINE language. Prefer short, concrete sentences.
- Describe what can be SEEN, HEARD, and FELT. Avoid confusing metaphors and overly ornate prose.
- Put ALL spoken dialogue inside double quotes, like: "Who goes there?" the guard shouted.
- Write narration (description, action, background) as normal sentences WITHOUT quotes.
- Ground every scene in the player character's established background and abilities.
- Introduce at most 1-2 new elements per turn so the player is never lost.
- Keep responses to 2-4 short paragraphs.
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

        world += "\nActive Characters:\n"
        for c in characters:
            cmeta = c.get("metadata") or {}
            stats = cmeta.get("stats", {})
            world += f"- {c['character_name']} ({c['role']}): Background: {c['background']}. Stats: {stats}\n"

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
                cap = 5 + bp["level"] * 5
                world += f"  Backpack: Level {bp['level']}, load {used}/{cap}\n"

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
