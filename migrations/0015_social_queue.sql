-- 0015_social_queue.sql — no schema change needed for the optimistic social layer.
-- Likes already use PK(story_id, user_id) which supports ON CONFLICT DO NOTHING
-- idempotent sets from the background queue. Kept as a ledger placeholder so the
-- migration ledger documents this sprint; safe to run repeatedly.
SELECT 1;
