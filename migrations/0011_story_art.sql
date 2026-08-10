-- 0011_story_art.sql — Phase 6 UI: story cover/banner art + NPC portraits
-- Additive-only; deploy-order safe (code falls back if columns absent).
ALTER TABLE stories ADD COLUMN IF NOT EXISTS cover_image TEXT NOT NULL DEFAULT '';
ALTER TABLE stories ADD COLUMN IF NOT EXISTS banner_image TEXT NOT NULL DEFAULT '';
ALTER TABLE story_characters ADD COLUMN IF NOT EXISTS image TEXT NOT NULL DEFAULT '';
