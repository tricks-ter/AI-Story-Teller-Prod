import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(BASE_DIR)
for _p in (PARENT_DIR, BASE_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from database import db
import db_ext

class PromptAssembler:
    def __init__(self, playthrough_id: str, max_chars: int = 40000):
        self.playthrough_id = playthrough_id
        self.max_chars = max_chars

    def assemble_full_prompt(self, user_action: str) -> str:
        pt = db.get_playthrough(self.playthrough_id)
        if not pt:
            return "You are a helpful assistant."
        story = db.get_story(pt["story_id"])
        if not story:
            return "You are a helpful assistant."

        state = db.get_full_playthrough_state(self.playthrough_id)
        characters = state["characters"]
        all_items = state["items"]
        all_equipment = state["equipment"]
        all_backpacks = state["backpacks"]

        # PHASE 6: Dynamic Context Fetching
        messages = db.get_recent_messages_for_context(self.playthrough_id, self.max_chars)
        memory = db.get_memory_summary(self.playthrough_id)
        lore = db.get_lorebook(self.playthrough_id)
        nudge = db.get_and_clear_nudge(self.playthrough_id)

        notes = db.get_story_notes(story["id"], active_only=True)

        system = f"""[SYSTEM INSTRUCTIONS]
You are a master storyteller and interactive fiction engine for a {story['genre']} RPG.
Write in 2nd-person present tense ("You draw your sword...").
Hidden state tags (own line):
  [TIME_UPDATE: Day X, TimeOfDay]
  [STAT_UPDATE: CharacterName.StatName = NewValue] / [STAT_UPDATE: CharacterName.StatName -10]
  [LOCATION_UPDATE: LocationName | desc=One-sentence chronicle of the place]
  [ITEM_UPDATE: CharacterName + ItemName | type=weapon, slot=main_hand, rarity=rare, level=4, weight=3, bonus.Health=10, desc=Short description]
  [ITEM_UPDATE: CharacterName - ItemName]
  [ABILITY_UPDATE: CharacterName + Ability Name | desc=What it does]
  [BAG_UPDATE: CharacterName level N]
  [WORLD_STATE_UPDATE: EntityName | kind=kingdom|family|npc|settlement, status=at_war, relationship=+10, power=70, wealth=500, is_alive=false, allegiance=House Vane]
  [WORLD_EVENT: EntityName | type=war|politics|economy|personal, desc=One sentence]
  [SAGA_END]  (ONLY when the player explicitly ends the story or a true ending is reached)
Item types: weapon, armor, accessory, consumable, material, quest.
Slots: main_hand, off_hand, head, body, ring, amulet, trinket.
Rarities: common, uncommon, rare, epic, legendary.

[STATE TAG RULES - CRITICAL]
- Physical objects -> ITEM_UPDATE. Powers/skills/soul rings/knowledge -> ABILITY_UPDATE (never in backpack).
- ALWAYS emit [LOCATION_UPDATE] (with desc=) when a location is first described, when the party moves, or when the player asks where they are. If no Current Location is set, infer it from the premise on your first response.
- Always include short desc= for new items, abilities and locations.
- Respect remaining backpack capacity — do not grant loot that won't fit.

[LIVING WORLD RULES - CRITICAL]
- The world is REAL and alive: kingdoms have conditions (prosperous, at_war, famine), families have standing (rising, disgraced), NPCs have feelings toward the player (relationship -100..100) and can die.
- Whenever a faction/kingdom/NPC situation changes in your narration, emit [WORLD_STATE_UPDATE] (use kind= on an entity's FIRST mention; signed numbers like relationship=+10 are deltas).
- For notable happenings (battles, edicts, betrayals, festivals, deaths) emit [WORLD_EVENT].
- Reference the [WORLD CODEX] below: previously met entities keep their names, grudges and states. Never contradict established world facts.

[PLAYER AGENCY RULES - CRITICAL]
- NEVER perform the player's chosen action for them, and NEVER describe its outcome.
- Stop at the moment of decision, or just as the action begins.
- The player is the only author of their character's choices.

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

        # PHASE 7: Procedural World Expansion Context
        loc_name = meta.get("current_location")
        if loc_name:
            node_ctx = db.get_node_context_for_location(self.playthrough_id, loc_name)
            if node_ctx:
                node = node_ctx["node"]
                children = node_ctx["children"]
                node_meta = node.get("metadata") or {}
                world += f"\n[LOCAL ENVIRONMENT: {node['name']}]\n"
                if node_meta.get("description"):
                    world += f"Description: {node_meta['description']}\n"
                if node_meta.get("economy"):
                    world += f"Economy: {node_meta['economy']}\n"
                if node_meta.get("politics"):
                    world += f"Politics/Factions: {node_meta['politics']}\n"

                if children:
                    world += "Local Entities:\n"
                    for child in children:
                        cmeta = child.get("metadata") or {}
                        desc = cmeta.get("description", "")
                        world += f"- {child['node_type'].upper()}: {child['name']}"
                        if desc: world += f" ({desc})"
                        world += "\n"

        # PHASE 7B: Living World Codex (kingdoms / families / NPCs with state)
        codex = db_ext.get_world_nodes_full(self.playthrough_id)
        if codex:
            world += "\n[WORLD CODEX - LIVING WORLD STATE]\n"
            for n in codex[:30]:
                line = f"- {str(n['node_type']).upper()} {n['name']}: status={n.get('status') or 'stable'}"
                if n["node_type"] == "npc":
                    rel = int(n.get("relationship") or 0)
                    line += f" | alive={'yes' if n.get('is_alive', True) else 'NO'} | relationship={rel:+d}"
                else:
                    line += f" | power={int(n.get('power') or 0)} | wealth={int(n.get('wealth') or 0)}"
                if n.get("allegiance"):
                    line += f" | allegiance={n['allegiance']}"
                world += line + "\n"

        events = db_ext.get_recent_world_events(self.playthrough_id, 8)
        if events:
            world += "\n[RECENT WORLD EVENTS]\n"
            for e in events:
                world += f"Day {e['day']} — {e['event_type']}: {e['description']} ({e['node_name']})\n"

        world += "\nActive Characters:\n"
        for c in characters:
            cmeta = c.get("metadata") or {}
            stats = cmeta.get("stats", {})
            world += f"- {c['character_name']} ({c['role']}): Background: {c['background']}. Stats: {stats}\n"

            abilities = cmeta.get("abilities", [])
            if isinstance(abilities, list) and abilities:
                world += "  Abilities: " + ", ".join(
                    a.get("name", "?") for a in abilities if isinstance(a, dict)) + "\n"

            char_items = [i for i in all_items if i["character_id"] == c["id"]]
            char_equip_ids = {e["item_id"] for e in all_equipment if e["character_id"] == c["id"]}
            carried = [i for i in char_items if i["id"] not in char_equip_ids]

            if carried:
                world += "  Carried: " + ", ".join(
                    f"{i['name']} ×{i['quantity']}" if i["quantity"] > 1 else i["name"] for i in carried) + "\n"

            equipped = [e for e in all_equipment if e["character_id"] == c["id"]]
            if equipped:
                world += "  Equipped: " + ", ".join(
                    f"{e['item_name']} ({e['slot']}, lv{e['item_level']})" for e in equipped) + "\n"

            bp = next((b for b in all_backpacks if b["character_id"] == c["id"]), None)
            if bp:
                used = sum(i["weight"] * i["quantity"] for i in carried)
                world += f"  Backpack: Level {bp['level']}, load {used}/{5 + bp['level'] * 5}\n"

        known = db.get_playthrough_map(self.playthrough_id)
        if known:
            world += "\nKnown Locations (journey so far): " + ", ".join(l["name"] for l in known) + "\n"

        context = "\n[STORY MEMORY & RECENT EVENTS]\n"
        if memory:
            context += f"[PREVIOUS CHAPTERS SUMMARY]\n{memory}\n\n"

        if lore:
            context += "[WORLD LOREBOOK]\n"
            for entry in lore[-15:]: # Keep last 15 entries in context
                context += f"- {entry.get('title', 'Lore')}: {entry.get('content', '')}\n"
            context += "\n"

        for m in messages:
            role = "Player" if m["role"] == "user" else "Narrator"
            context += f"{role}: {m['content']}\n"

        if nudge:
            context += f"\n{ nudge }\n"

        director = ""
        if notes:
            director = "\n[DIRECTOR'S NOTES - High Priority Overrides]\n"
            for n in notes:
                director += f"- {n['content']}\n"

        action = f"\n[PLAYER'S CURRENT ACTION]\n{user_action}\n\nRespond with clear, immersive narrative prose. Stop before the outcome."

        return system + world + context + director + action
