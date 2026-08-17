# DATABASE MASTER CONTRACT — InkMind (PostgreSQL)
> Verified against commit f32ebcc (branch main, 2026-08-13), migrations 0001–0013.
>
> GOVERNANCE (immutable): (1) APPEND-ONLY — never remove entries or restructure unless the user
> explicitly orders it. (2) Any schema change = new numbered migration in migrations/ (IF NOT EXISTS,
> deploy-order safe) + updated §3 row + §5 matrix + BACKEND_MASTER notes. Never runtime DDL.
> (3) Every INSERT fills every column (no NULLs; defaults everywhere). IDs are VARCHAR(36). JSONB for
> AI-invented dynamic data. Per-user isolation on all reads/writes.

## 1. DESIGN RULES
- IDs: VARCHAR(36) (uuid4 strings; some seeded via substr(md5(random()::text...),1,36)).
- JSONB for dynamic AI data (stats/abilities/inventory-mirror/bonuses/lore/memory).
- story_messages.playthrough_id='legacy' = author template rows (security boundary; base_only reads). Real saga rows carry the playthrough id.
- LEGACY_USER_ID = 'legacy-system' (seeded user row) owns pre-auth content; claimable.
- Capacity: backpack = 5 + level×5; equipped items weigh nothing; quest items undroppable.
- Triggers set_updated_at() maintain updated_at on: stories, playthroughs, locations, chat_sessions, playthrough_items, playthrough_backpacks.

## 2. ENTITY RELATIONS
users 1-N auth_tokens
users 1-N playthroughs ; users 1-N stories(creator_id) ; users 1-N chat_sessions 1-N chat_messages
stories 1-N story_characters | story_messages('legacy') | story_notes | playthroughs
playthroughs 1-N playthrough_characters | locations | story_messages | world_nodes | world_events
playthrough_characters 1-N playthrough_items | playthrough_equipment ; 1-1 playthrough_backpacks
playthrough_items 1-N playthrough_equipment (UNIQUE(character_id, slot))
world_nodes self-ref via parent_id (e.g. settlement → building → npc)

## 3. TABLES (columns · constraints · indexes)
### users
id PK · username UNIQUE NOT NULL · password_hash NOT NULL · role NOT NULL DEFAULT 'user' · metadata JSONB DEFAULT '{}' · created_at. Seeded row legacy-system.
### auth_tokens
token VARCHAR(128) PK · user_id FK→users CASCADE · expires_at TIMESTAMPTZ · created_at. idx(user_id).
### chat_sessions
id PK · title NOT NULL · user_id DEFAULT 'legacy-system' · created_at · updated_at. idx(user_id).
### chat_messages
id SERIAL PK · session_id FK→chat_sessions CASCADE · role CHECK(user|assistant|system) · content TEXT · user_id DEFAULT 'legacy-system' · metadata JSONB · created_at. idx(session_id,id).
### stories
id PK · title NOT NULL · genre DEFAULT 'Unknown' · premise DEFAULT '' · current_day DEFAULT 1 CHECK≥1 · time_of_day DEFAULT 'Morning' · creator_id DEFAULT 'legacy-system' · is_premium DEFAULT FALSE · energy_cost DEFAULT 0 · is_public DEFAULT TRUE (0007) · cover_image TEXT DEFAULT '' (0011_story_art) · banner_image TEXT DEFAULT '' (0011_story_art) · metadata JSONB · created_at · updated_at. idx(is_public).
### story_characters
id PK · story_id FK→stories CASCADE · name NOT NULL · role DEFAULT 'Character' · background DEFAULT '' · is_player DEFAULT TRUE · image TEXT DEFAULT '' (0011_story_art) · metadata JSONB(stats/inventory seed) · created_at. idx(story_id).
### story_messages
id SERIAL PK · story_id FK→stories CASCADE · role CHECK · content TEXT · message_type DEFAULT 'narration' (intro|action|narration) · metadata JSONB · created_at · playthrough_id VARCHAR(36) DEFAULT 'legacy' (0002). idx(story_id,id), idx(playthrough_id,id).
### story_notes
id SERIAL PK · story_id FK→stories CASCADE · content TEXT · priority INT DEFAULT 5 · is_active DEFAULT TRUE · created_at. idx(story_id).
### playthroughs
id PK · story_id FK CASCADE · user_id FK→users CASCADE · current_day DEFAULT 1 CHECK≥1 · time_of_day DEFAULT 'Morning' · status DEFAULT 'active' CHECK(active|completed|abandoned|paused) · metadata JSONB (current_location, memory_summary, lorebook, active_nudge — see D-1) · created_at · updated_at. idx(user_id,status), idx(story_id,user_id). + dormant columns memory_summary TEXT, lorebook JSONB, active_nudge TEXT (0011_memory_and_lore).
### playthrough_characters
id PK · playthrough_id FK CASCADE · character_name NOT NULL · role · background · is_player · metadata JSONB(stats/abilities/inventory mirror) · created_at. idx(playthrough_id).
### locations
id PK · playthrough_id FK CASCADE · name NOT NULL · description DEFAULT '' · is_discovered DEFAULT FALSE (set TRUE on upsert) · metadata JSONB · created_at · updated_at · visit_count INT DEFAULT 1 (0009) · last_visited_at (0009). UNIQUE(playthrough_id, LOWER(name)) (0004/0005 + 0010 explicit).
### playthrough_items
id PK · playthrough_id FK CASCADE · character_id FK→playthrough_characters CASCADE · name NOT NULL · item_type CHECK(weapon|armor|accessory|consumable|material|quest) · slot CHECK(''|main_hand|off_hand|head|body|ring|amulet|trinket) · rarity CHECK(common..legendary) · item_level 1..99 · weight 0..99 · quantity 1..99 · metadata JSONB(description, bonuses) · created_at · updated_at. idx(playthrough_id), idx(character_id).
### playthrough_equipment
id PK · playthrough_id FK CASCADE · character_id FK CASCADE · item_id FK→playthrough_items CASCADE · slot · created_at. UNIQUE(character_id, slot). idx(playthrough_id), idx(character_id).
### playthrough_backpacks
id PK · playthrough_id FK CASCADE · character_id FK CASCADE UNIQUE · level 1..20 DEFAULT 1 · metadata JSONB · created_at · updated_at. idx(playthrough_id).
### world_nodes (0012 + 0013)
id PK · playthrough_id FK→playthroughs CASCADE · parent_id FK→world_nodes CASCADE (NULL=root) · node_type CHECK(region|faction|settlement|location|npc|item|economy_state) · name NOT NULL · metadata JSONB(description/economy/politics) · status VARCHAR(64) DEFAULT 'stable' · is_alive BOOL DEFAULT TRUE · relationship INT DEFAULT 0 (−100..100 app-clamped) · wealth INT DEFAULT 0 · power INT DEFAULT 50 (0..100) · allegiance VARCHAR(255) DEFAULT '' · last_state_change_at · created_at · updated_at. UNIQUE(playthrough_id, node_type, LOWER(name)); idx(parent_id); idx(playthrough_id, node_type).
### world_events (0013)
id PK · playthrough_id FK CASCADE · node_id VARCHAR(36) DEFAULT '' · node_name DEFAULT '' · event_type DEFAULT 'event' (war|politics|economy|personal|…) · description TEXT DEFAULT '' · day INT DEFAULT 1 · created_at. idx(playthrough_id, day DESC, created_at DESC).
### schema_migrations (created by migrate.py)
filename VARCHAR(255) PK · applied_at TIMESTAMPTZ DEFAULT NOW.

## 4. MIGRATION LEDGER
| File | Effect |
|---|---|
| 0001_core_schema.sql | users(+legacy seed), auth_tokens, chat_sessions, chat_messages, stories, story_characters, story_messages, story_notes |
| 0002_playthroughs.sql | playthroughs, playthrough_characters; story_messages.playthrough_id + backfill legacy stories |
| 0003_hardening.sql | NOT NULL + defaults everywhere; role CHECK on messages |
| 0004_locations_hud.sql | locations + indexes |
| 0005_robustness.sql | hot-path indexes, CHECKs (status/day/role), updated_at triggers, unique location name |
| 0006_items_equipment.sql | playthrough_items/equipment/backpacks + CHECKs + unique slot/backpack |
| 0007_visibility.sql | stories.is_public |
| 0009_map_completion.sql | locations.visit_count / last_visited_at |
| 0010_location_upsert_index.sql | explicit unique index for ON CONFLICT upsert |
| 0011_memory_and_lore.sql | playthroughs memory_summary/lorebook/active_nudge (dormant, see D-1) |
| 0011_story_art.sql | stories.cover_image/banner_image, story_characters.image |
| 0012_world_nodes.sql | world_nodes graph + unique name index |
| 0013_world_state.sql | world_nodes state columns + world_events ledger |
(0008_story_indexes.sql is referenced by old docs but ABSENT from repo — see D-2. Two files share number 0011; ledger tracks filenames so both apply.)

## 5. METHOD → TABLE MATRIX (who touches what)
### api/database.py (db.*)
| Methods | Tables |
|---|---|
| create_user_with_token, create_user, get_user_by_username, get_user_by_id, touch_user_login, update_user_metadata | users |
| add_auth_token, delete_auth_token, purge_expired_tokens | auth_tokens |
| ensure_session | chat_sessions |
| add_message, get_last_session_message | chat_messages |
| create_story, set_story_visibility, get_story, list_stories_for_user, list_all_stories, update_story_time, update_story_location | stories (+users join for creator_name; +story_characters/playthroughs subselects) |
| add_story_character, get_story_characters, update_character_stat | story_characters |
| add_story_message, get_story_messages | story_messages |
| get_story_notes, list_story_notes_full, add_story_note, toggle_story_note, delete_story_note | story_notes |
| get_active_playthrough, get_playthrough, complete_playthrough, create_playthrough, list_playthroughs_for_user, update_playthrough_time, update_playthrough_location, get_memory_summary, get_lorebook, get_and_clear_nudge | playthroughs (+stories/chars subselects in list) |
| get_playthrough_characters, update_playthrough_character_stat/ability/inventory, _sync_inventory_mirror | playthrough_characters |
| add_playthrough_message, get_playthrough_messages, get_last_playthrough_message, get_recent_messages_for_context | story_messages (playthrough-scoped) |
| upsert_playthrough_location, get_playthrough_locations, get_playthrough_map | locations (+playthroughs.metadata.current_location) |
| ensure_playthrough_inventory, list_playthrough_items, list_carried_items_for_character, backpack_used_capacity, grant_playthrough_item, consume_playthrough_item, use_item, drop_item | playthrough_items (+equipment subselect, +backpacks for capacity) |
| list_playthrough_equipment, list_equipment_for_character, compute_equipped_bonuses, equip_item, unequip_item | playthrough_equipment (+playthrough_items, +backpacks) |
| get_backpack_for_character, list_playthrough_backpacks, set_playthrough_backpack_level | playthrough_backpacks |
| get_full_playthrough_state | playthrough_characters + items + equipment + backpacks (batch) |
| get_world_nodes, bulk_insert_world_nodes, get_node_context_for_location | world_nodes |
### api/db_ext.py
| Functions | Tables |
|---|---|
| set_story_art, set_story_banner, get_all_story_art, update_story_fields | stories |
| set_character_image, get_cast_with_images | story_characters |
| find_stackable_item, bump_item_quantity, dedupe_stackables | playthrough_items (+playthrough_equipment cleanup) |
| get_world_nodes_full, ensure_world_node, update_world_node_state | world_nodes |
| record_world_event, get_recent_world_events | world_events (+world_nodes lookup) |
| set_memory_summary | playthroughs.metadata |
### api/core/auth.py & migrate.py
get_user_by_token → auth_tokens JOIN users · migrate.py → schema_migrations + applies migrations/*.sql.

## 6. BUSINESS INVARIANTS (enforced in code, not just schema)
- Stat values clamped 0..999 (applier/db). HP deltas: resolver marks signed values is_delta; applier adds to current. (Frontend mirror has pending fix FE-BUG-1.)
- relationship −100..100 · power 0..100 · wealth 0..9,999,999 · item quantity ≤99 (schema) / ≤9999 (dedupe bump cap).
- Stackables (consumable/material) must stack: grant_playthrough_item stacks by (name,type); state_applier bumps existing rows; dedupe_stackables self-heals on every inventory read.
- Equipment: one item per (character, slot); equip swaps with capacity math; equipped items excluded from weight.
- Backpack capacity 5+5×level; grants/equips/unequips refuse when over capacity (backpack_full).
- World entity names unique per (playthrough, node_type, LOWER(name)); descriptions fill-only-when-empty (first chronicle wins); LOCATION_UPDATE always registers a settlement node (anti-hallucination persistence).
- Cross-user isolation: all playthrough endpoints check user_id; story lists filter creator_id/is_public; 'legacy' rows never leak into other users' sagas (base_only reads + per-playthrough seeding).

## 7. KNOWN DISCREPANCIES (resolve; don't delete until fixed)
- D-1: memory/lore/nudge stored in playthroughs.metadata JSONB while dedicated columns exist (0011_memory_and_lore) — columns dormant. Decide canonical storage.
- D-2: 0008_story_indexes.sql missing from repo (old docs reference it) — verify production indexes if query plans degrade.
- D-3: world_nodes unique key includes node_type, but update_world_node_state looks up by name only across types (BACKEND B-3).
- D-4: quick-chat chat_sessions/chat_messages are written by backend but UI history is localStorage-only (no session listing endpoint/UI).

## 8. MAINTENANCE RULES
- New migration: next number (0014…), IF NOT EXISTS, additive columns with NOT NULL DEFAULT, test with migrate.yml on push.
- New table → add §3 block + §2 relation + §5 rows for every method that touches it.
- New JSONB key used by code → list it under the table's entry (e.g. playthroughs.metadata.*).
- Never drop/rename columns without a user-approved plan (additive-only project).
