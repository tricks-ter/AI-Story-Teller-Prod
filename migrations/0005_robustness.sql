-- 0005: Robustness — indexes, integrity constraints, triggers, race-proof locations

-- Hot-path indexes (query performance)
CREATE INDEX IF NOT EXISTS idx_story_messages_playthrough ON story_messages(playthrough_id, id);
CREATE INDEX IF NOT EXISTS idx_story_messages_story ON story_messages(story_id, id);
CREATE INDEX IF NOT EXISTS idx_playthroughs_user_status ON playthroughs(user_id, status);
CREATE INDEX IF NOT EXISTS idx_playthroughs_story_user ON playthroughs(story_id, user_id);
CREATE INDEX IF NOT EXISTS idx_playthrough_characters_pt ON playthrough_characters(playthrough_id);
CREATE INDEX IF NOT EXISTS idx_story_characters_story ON story_characters(story_id);
CREATE INDEX IF NOT EXISTS idx_auth_tokens_user ON auth_tokens(user_id);
CREATE INDEX IF NOT EXISTS idx_chat_messages_session ON chat_messages(session_id, id);
CREATE INDEX IF NOT EXISTS idx_story_notes_story ON story_notes(story_id);
CREATE INDEX IF NOT EXISTS idx_chat_sessions_user ON chat_sessions(user_id);

-- Race-proof location discovery (supports ON CONFLICT upsert)
CREATE UNIQUE INDEX IF NOT EXISTS uniq_locations_playthrough_name ON locations(playthrough_id, LOWER(name));

-- Integrity constraints (all existing data complies)
ALTER TABLE playthroughs DROP CONSTRAINT IF EXISTS chk_playthroughs_status;
ALTER TABLE playthroughs ADD CONSTRAINT chk_playthroughs_status
    CHECK (status IN ('active','completed','abandoned','paused'));
ALTER TABLE playthroughs DROP CONSTRAINT IF EXISTS chk_playthroughs_day;
ALTER TABLE playthroughs ADD CONSTRAINT chk_playthroughs_day CHECK (current_day >= 1);
ALTER TABLE stories DROP CONSTRAINT IF EXISTS chk_stories_day;
ALTER TABLE stories ADD CONSTRAINT chk_stories_day CHECK (current_day >= 1);
ALTER TABLE story_messages DROP CONSTRAINT IF EXISTS chk_story_messages_role;
ALTER TABLE story_messages ADD CONSTRAINT chk_story_messages_role
    CHECK (role IN ('user','assistant','system'));

-- Auto-maintain updated_at on every UPDATE
CREATE OR REPLACE FUNCTION set_updated_at() RETURNS trigger AS $$
BEGIN
  NEW.updated_at = CURRENT_TIMESTAMP;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_stories_updated_at ON stories;
CREATE TRIGGER trg_stories_updated_at BEFORE UPDATE ON stories
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
DROP TRIGGER IF EXISTS trg_playthroughs_updated_at ON playthroughs;
CREATE TRIGGER trg_playthroughs_updated_at BEFORE UPDATE ON playthroughs
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
DROP TRIGGER IF EXISTS trg_locations_updated_at ON locations;
CREATE TRIGGER trg_locations_updated_at BEFORE UPDATE ON locations
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
DROP TRIGGER IF EXISTS trg_chat_sessions_updated_at ON chat_sessions;
CREATE TRIGGER trg_chat_sessions_updated_at BEFORE UPDATE ON chat_sessions
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
