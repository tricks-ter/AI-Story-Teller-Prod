-- 0007: Story visibility
ALTER TABLE stories ADD COLUMN IF NOT EXISTS is_public BOOLEAN NOT NULL DEFAULT TRUE;
CREATE INDEX IF NOT EXISTS idx_stories_public ON stories(is_public);
