CREATE TABLE IF NOT EXISTS playthroughs (
    id VARCHAR(36) PRIMARY KEY,
    story_id VARCHAR(36) NOT NULL REFERENCES stories(id) ON DELETE CASCADE,
    user_id VARCHAR(36) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    current_day INT NOT NULL DEFAULT 1,
    time_of_day VARCHAR(50) NOT NULL DEFAULT 'Morning',
    status VARCHAR(20) NOT NULL DEFAULT 'active',
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS playthrough_characters (
    id VARCHAR(36) PRIMARY KEY,
    playthrough_id VARCHAR(36) NOT NULL REFERENCES playthroughs(id) ON DELETE CASCADE,
    character_name VARCHAR(255) NOT NULL,
    role VARCHAR(100) NOT NULL DEFAULT 'Character',
    background TEXT NOT NULL DEFAULT '',
    is_player BOOLEAN NOT NULL DEFAULT TRUE,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP);
ALTER TABLE story_messages ADD COLUMN IF NOT EXISTS playthrough_id VARCHAR(36) NOT NULL DEFAULT 'legacy';

DO $$
DECLARE s RECORD; p VARCHAR(36);
BEGIN
  FOR s IN SELECT id, creator_id, current_day, time_of_day FROM stories LOOP
    IF NOT EXISTS (SELECT 1 FROM playthroughs p2 WHERE p2.story_id = s.id) THEN
      p := substr(md5(random()::text || s.id), 1, 36);
      INSERT INTO playthroughs (id, story_id, user_id, current_day, time_of_day, status, metadata, created_at, updated_at)
      VALUES (p, s.id, s.creator_id, s.current_day, s.time_of_day, 'active', '{}', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP);
      UPDATE story_messages SET playthrough_id = p WHERE story_id = s.id AND playthrough_id = 'legacy';
      INSERT INTO playthrough_characters (id, playthrough_id, character_name, role, background, is_player, metadata, created_at)
      SELECT substr(md5(random()::text || sc.id), 1, 36), p, sc.name, sc.role, sc.background, sc.is_player, sc.metadata, CURRENT_TIMESTAMP
      FROM story_characters sc WHERE sc.story_id = s.id;
    END IF;
  END LOOP;
END $$;
