-- Phase 6: Rolling Memory, Lorebook, and Consumable Nudges
ALTER TABLE playthroughs ADD COLUMN IF NOT EXISTS memory_summary TEXT DEFAULT '';
ALTER TABLE playthroughs ADD COLUMN IF NOT EXISTS lorebook JSONB DEFAULT '[]';
ALTER TABLE playthroughs ADD COLUMN IF NOT EXISTS active_nudge TEXT DEFAULT '';
