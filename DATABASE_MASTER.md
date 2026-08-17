# DATABASE MASTER CONTRACT — InkMind (PostgreSQL)
> Verified vs migrations 0001–0013. APPEND-ONLY. Schema change = new numbered
> migration (IF NOT EXISTS) + §3 row + §4 matrix + BACKEND notes. Never runtime DDL.
> IDs VARCHAR(36) · JSONB for AI-invented data · every INSERT fills every column ·
> per-user isolation on all reads/writes.

## 1. RELATIONS
users 1-N auth_tokens|playthroughs|stories(creator)|chat_sessions 1-N chat_messages
stories 1-N story_characters|story_messages('legacy')|story_notes|playthroughs
playthroughs 1-N playthrough_characters|locations|story_messages|world_nodes|world_events
playthrough_characters 1-N playthrough_items|playthrough_equipment ; 1-1 playthrough_backpacks
playthrough_items 1-N playthrough_equipment (UNIQUE(character_id,slot))
world_nodes self-ref parent_id (settlement→building→npc)

## 2. TABLES (key columns)
users(id, username UNIQ, password_hash, role, metadata, created) + seeded legacy-system
auth_tokens(token PK, user_id FK, expires_at)
chat_sessions(id, title, user_id def legacy) · chat_messages(id SERIAL, session_id FK, role CHECK, content, user_id, metadata)
stories(id, title, genre def Unknown, premise, current_day≥1, time_of_day, creator_id def legacy, is_premium, energy_cost, is_public def TRUE(0007), cover_image/banner_image def ''(0011_story_art), metadata JSONB)
story_characters(id, story_id FK, name, role, background, is_player, image def ''(0011_story_art), metadata)
story_messages(id SERIAL, story_id FK, role CHECK, content, message_type, metadata, playthrough_id def 'legacy'(0002))
story_notes(id SERIAL, story_id FK, content, priority, is_active)
playthroughs(id, story_id FK, user_id FK, current_day, time_of_day, status CHECK(active|completed|abandoned|paused), metadata(current_location/memory_summary/lorebook/active_nudge), + dormant columns memory_summary/lorebook/active_nudge(0011_memory_and_lore))
playthrough_characters(id, playthrough_id FK, character_name, role, background, is_player, metadata)
locations(id, playthrough_id FK, name, description, is_discovered, visit_count, last_visited_at, metadata; UNIQUE(playthrough_id, LOWER(name)))
playthrough_items(id, playthrough_id FK, character_id FK, name, item_type CHECK, slot CHECK, rarity CHECK, item_level 1..99, weight 0..99, quantity 1..99, metadata)
playthrough_equipment(id, playthrough_id FK, character_id FK, item_id FK, slot; UNIQUE(character_id,slot))
playthrough_backpacks(id, playthrough_id FK, character_id FK UNIQUE, level 1..20, metadata)
world_nodes(id, playthrough_id FK, parent_id self-FK, node_type CHECK(region|faction|settlement|location|npc|item|economy_state), name, metadata, status def stable, is_alive, relationship def 0, wealth def 0, power def 50, allegiance def '', last_state_change_at; UNIQUE(playthrough_id,node_type,LOWER(name)))
world_events(id, playthrough_id FK, node_id def '', node_name def '', event_type def 'event', description def '', day def 1)
schema_migrations(filename PK, applied_at)

## 3. TRIGGERS & CONSTRAINTS
set_updated_at() triggers on stories, playthroughs, locations, chat_sessions, playthrough_items, playthrough_backpacks. CHECKs as listed above.

## 4. METHOD → TABLE MATRIX
database.py: auth→users/auth_tokens · chat→chat_* · stories→stories(+users join)/story_characters/story_messages · notes→story_notes · playthroughs→playthroughs/playthrough_characters/story_messages · locations→locations(+playthroughs.metadata) · char state→playthrough_characters.metadata · inventory→playthrough_items/equipment/backpacks · phase6→story_messages/playthroughs.metadata · phase7→world_nodes.
db_ext.py: art/fields/metadata→stories · character image/edit→story_characters · stackables→playthrough_items(+equipment cleanup) · world→world_nodes · events→world_events · memory→playthroughs.metadata.
core/auth.py→auth_tokens JOIN users · migrate.py→schema_migrations + migrations/*.sql.

## 5. MIGRATION LEDGER
0001 core(+legacy seed) · 0002 playthroughs+playthrough_id+backfill · 0003 hardening · 0004 locations · 0005 robustness(indexes/CHECKs/triggers/uniq location) · 0006 items/equipment/backpacks · 0007 is_public · 0009 visit_count/last_visited_at · 0010 location upsert index · 0011_memory_and_lore(dormant) · 0011_story_art(cover/banner/image) · 0012 world_nodes · 0013 world state columns + world_events. (0008 absent; two 0011s apply — ledger tracks filenames.)

## 6. BUSINESS INVARIANTS
Backpack capacity 5+5×level; equipped weigh nothing; quest undroppable; stackables must stack (grant stacks, applier bumps, dedupe self-heals); world names unique per (pt,type,lower); descriptions fill-only-when-empty; LOCATION_UPDATE registers settlement node; legacy rows never leak (base_only + per-playthrough seeding); stat clamps backend 0..999 / frontend 0..Max*(D-5).

## 7. DISCREPANCY LEDGER
- D-1 memory columns dormant vs metadata JSONB — OPEN.
- D-2 0008 missing — OPEN.
- D-3 world_nodes unique incl node_type vs name-only upsert in update_world_node_state — ACCEPTED.
- D-4 quick-chat UI localStorage-only — OPEN.
- D-5 dual stat clamps — ACCEPTED.

## 8. MAINTENANCE RULES
New table → §2 + §1 + §4 rows. New JSONB key → note under table. Never drop/rename columns without user-approved plan.
