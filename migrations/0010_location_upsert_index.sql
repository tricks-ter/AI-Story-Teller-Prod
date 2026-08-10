-- Phase 6 Audit Fix: Prevent fatal Postgres "ON CONFLICT" planning errors
-- This creates the exact functional unique index required by upsert_playthrough_location
CREATE UNIQUE INDEX IF NOT EXISTS idx_locations_playthrough_lower_name 
ON locations (playthrough_id, LOWER(name));
