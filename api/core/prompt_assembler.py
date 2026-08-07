from database import db

class PromptAssembler:
    def __init__(self, story_id: str):
        self.story_id = story_id

    def get_story_context(self):
        story = db.execute_query("SELECT * FROM stories WHERE id = %s", (self.story_id,), fetch="one")
        chars = db.execute_query("SELECT * FROM story_characters WHERE story_id = %s", (self.story_id,), fetch="all")
        msgs = db.execute_query("SELECT role, content FROM story_messages WHERE story_id = %s ORDER BY created_at DESC LIMIT 10", (self.story_id,), fetch="all")
        return story, chars, msgs

    def assemble_prompt(self, user_action: str):
        story, chars, msgs = self.get_story_context()
        if not story: return "You are a helpful assistant."
        
        prompt = f"System: You are a master storyteller in a {story['genre']} RPG. The story is '{story['title']}'.\n"
        prompt += f"Premise: {story['premise']}\n"
        prompt += f"Current Day: {story['current_day']}, Time: {story['time_of_day']}\n"
        
        if chars:
            prompt += "Characters in scene:\n"
            for c in chars:
                stats = c.get('metadata', {}).get('stats', {}) if isinstance(c.get('metadata'), dict) else {}
                prompt += f"- {c['name']} ({c['role']}): Background: {c['background']}. Stats: {stats}\n"
                
        prompt += "\nRecent History:\n"
        for m in reversed(msgs):
            prompt += f"{m['role']}: {m['content']}\n"
            
        prompt += f"\nPlayer Action: {user_action}\n"
        prompt += "Respond with immersive 2nd-person prose. Use hidden tags like [TIME_UPDATE: Day X, TimeOfDay] if time passes."
        return prompt
