-- Migration 0008: Composite and Performance Indexes for Stories, Playthroughs & Social
CREATE INDEX IF NOT EXISTS idx_story_messages_pt_id ON story_messages(playthrough_id, id ASC);
CREATE INDEX IF NOT EXISTS idx_story_messages_story_id ON story_messages(story_id);
CREATE INDEX IF NOT EXISTS idx_playthrough_equipment_char ON playthrough_equipment(character_id, slot);
CREATE INDEX IF NOT EXISTS idx_playthrough_items_char ON playthrough_items(character_id);
CREATE INDEX IF NOT EXISTS idx_stories_creator_updated ON stories(creator_id, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_stories_public_updated ON stories(is_public, updated_at DESC);
