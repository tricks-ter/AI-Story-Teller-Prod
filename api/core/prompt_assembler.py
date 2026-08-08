import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(BASE_DIR)
for _p in (PARENT_DIR, BASE_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from database import db

class PromptAssembler:
    def __init__(self, story_id: str):
        self.story_id = story_id

    def assemble_full_prompt(self, user_action: str) -> str:
        story = db.get_story(self.story_id)
        if not story:
            return "You are a helpful assistant."

        characters = db.get_story_characters(self.story_id)
        messages = db.get_story_messages(self.story_id, limit=15)
        notes = db.get_story_notes(self.story_id, active_only=True)

        system = f"""[SYSTEM INSTRUCTIONS]
You are a master storyteller and interactive fiction engine for a {story['genre']} RPG.
Write in 2nd-person present tense ("You draw your sword...").
You may use hidden state tags on their own line to update world state:
  [TIME_UPDATE: Day X, TimeOfDay]  (Morning/Afternoon/Evening/Night)
  [STAT_UPDATE: CharacterName.StatName = NewValue]
  [STAT_UPDATE: CharacterName.StatName -10]
  [LOCATION_UPDATE: NewLocationName]
Use tags sparingly, only when the narrative justifies it.

[STYLE RULES - CRITICAL]
- Write in CLEAR, SIMPLE, EASY-TO-IMAGINE language. Prefer short, concrete sentences.
- Describe what can be SEEN, HEARD, and FELT. Avoid confusing metaphors and overly ornate prose.
- Put ALL spoken dialogue inside double quotes, like: "Who goes there?" the guard shouted.
- Write narration (description, action, background) as normal sentences WITHOUT quotes.
- Ground every scene in the player character's established background and abilities.
- Introduce at most 1-2 new elements per turn so the player is never lost.
- Keep responses to 2-4 short paragraphs and end with a clear moment or choice.
"""

        world = f"""[WORLD STATE]
Story: {story['title']}
Premise: {story['premise']}
Current Day: {story['current_day']}
Time of Day: {story['time_of_day']}
"""
        meta = story.get("metadata") or {}
        if meta.get("current_location"):
            world += f"Current Location: {meta['current_location']}\n"

        world += "\nActive Characters:\n"
        for c in characters:
            cmeta = c.get("metadata") or {}
            stats = cmeta.get("stats", {})
            inv = cmeta.get("inventory", [])
            world += f"- {c['name']} ({c['role']}): Background: {c['background']}. Stats: {stats}. Inventory: {inv}\n"

        context = "\n[RECENT STORY CONTEXT]\n"
        for m in messages:
            role = "Player" if m["role"] == "user" else "Narrator"
            context += f"{role}: {m['content']}\n"

        director = ""
        if notes:
            director = "\n[DIRECTOR'S NOTES - High Priority Overrides]\n"
            for n in notes:
                director += f"- {n['content']}\n"

        action = f"\n[PLAYER'S CURRENT ACTION]\n{user_action}\n\nRespond with clear, immersive narrative prose."

        return system + world + context + director + action
