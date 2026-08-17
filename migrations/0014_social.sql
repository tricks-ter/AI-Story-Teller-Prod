-- 0014_social.sql — Social layer: likes + comments
-- Additive-only; deploy-order safe.
CREATE TABLE IF NOT EXISTS story_likes (
    story_id VARCHAR(36) NOT NULL REFERENCES stories(id) ON DELETE CASCADE,
    user_id VARCHAR(36) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (story_id, user_id)
);
CREATE INDEX IF NOT EXISTS idx_story_likes_story ON story_likes(story_id);

CREATE TABLE IF NOT EXISTS story_comments (
    id SERIAL PRIMARY KEY,
    story_id VARCHAR(36) NOT NULL REFERENCES stories(id) ON DELETE CASCADE,
    user_id VARCHAR(36) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    username VARCHAR(80) NOT NULL DEFAULT 'Adventurer',
    content TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_story_comments_story ON story_comments(story_id, created_at DESC);
