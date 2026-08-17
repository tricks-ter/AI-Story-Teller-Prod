# DATABASE MASTER CONTRACT — InkMind (PostgreSQL)
> Verified against commit f32ebcc migrations 0001–0013.
> GOVERNANCE: APPEND-ONLY. Schema change = new numbered migration (IF NOT EXISTS,
> deploy-order safe) + update §2 + §4 + BACKEND_MASTER notes. Never runtime DDL.
> Every INSERT fills every column (no NULLs, defaults everywhere). IDs VARCHAR(36). JSONB for dynamic AI data. Per-user isolation on all reads/writes.

## 1. DESIGN RULES & RELATIONS
users 1-N auth_tokens · users 1-N playthroughs · users 1-N stories(creator_id) · users 1-N chat_sessions 1-N chat_messages · stories 1-N story_characters | story_messages('legacy') | story_notes | playthroughs · playthroughs 1-N playthrough_characters | locations | story_messages | world_nodes | world_events · playthrough_characters 1-N playthrough_items | playthrough_equipment ; 1-1 playthrough_backpacks · playthrough_items 1-N playthrough_equipment (UNIQUE(character_id,slot)) · world_nodes self-ref parent_id.
story_messages.playthrough_id='legacy' = author template rows (security boundary). LEGACY_USER_ID='legacy-system' seeded user. Triggers set_updated_at on stories, playthroughs, locations, chat_sessions, playthrough_items, playthrough_backpacks.

## 2. TABLES
- users: id PK, username UNIQUE, password_hash, role default 'user', metadata JSONB (energy_credits, telemetry), created_at.
- auth_tokens: token PK, user_id FK CASCADE, expires_at, created_at.
- chat_sessions: id PK, title, user_id default legacy, created_at, updated_at.
- chat_messages: id SERIAL, session_id FK, role CHECK(user|assistant|system), content, user_id default legacy, metadata, created_at.
- stories: id PK, title, genre default 'Unknown', premise default '', current_day default 1 (CHECK ≥1), time_of_day default 'Morning', creator_id default legacy, is_premium FALSE, energy_cost 0, is_public TRUE (0007), cover_image TEXT '' (0011_story_art), banner_image TEXT '' (0011_story_art), metadata JSONB, created_at, updated_at.
- story_characters: id PK, story_id FK, name, role default 'Character', background '', is_player TRUE, image TEXT '' (0011_story_art), metadata JSONB (stats: Health/MaxHealth/Mana/MaxMana + inventory seed; new sagas seed MaxHealth=100, MaxMana=50), created_at.
- story_messages: id SERIAL, story_id FK, role CHECK, content, message_type default 'narration' (intro|action|narration), metadata, created_at, playthrough_id default 'legacy' (0002).
- story_notes: id SERIAL, story_id FK, content, priority default 5, is_active TRUE, created_at.
- playthroughs: id PK, story_id FK, user_id FK, current_day CHECK≥1, time_of_day, status CHECK(active|completed|abandoned|paused) default active, metadata JSONB (current_location, memory_summary, lorebook, active_nudge — see D-1), created_at, updated_at. Dormant columns: memory_summary, lorebook, active_nudge (0011_memory_and_lore).
- playthrough_characters: id PK, playthrough_id FK, character_name, role, background, is_player, metadata JSONB(stats/abilities/inventory mirror), created_at.
- locations: id PK, playthrough_id FK, name, description '', is_discovered, metadata, visit_count default 1 (0009), last_visited_at (0009), created_at, updated_at. UNIQUE(playthrough_id, LOWER(name)) (0010).
- playthrough_items: id PK, playthrough_id FK, character_id FK, name, item_type CHECK(weapon|armor|accessory|consumable|material|quest), slot CHECK, rarity CHECK(common..legendary), item_level 1..99, weight 0..99, quantity 1..99, metadata JSONB(description, bonuses), created_at, updated_at.
- playthrough_equipment: id PK, playthrough_id FK, character_id FK, item_id FK, slot, created_at. UNIQUE(character_id, slot).
- playthrough_backpacks: id PK, playthrough_id FK, character_id FK UNIQUE, level 1..20 default 1, metadata, created_at, updated_at. Capacity formula 5+5×level (code).
- world_nodes (0012+0013): id PK, playthrough_id FK, parent_id self-FK NULL=root, node_type CHECK(region|faction|settlement|location|npc|item|economy_state), name, metadata JSONB(description/economy/politics), status default 'stable', is_alive TRUE, relationship default 0, wealth default 0, power default 50, allegiance '', last_state_change_at, created_at, updated_at. UNIQUE(playthrough_id,node_type,LOWER(name)); idx(parent_id); idx(playthrough_id,node_type).
- world_events (0013): id PK, playthrough_id FK, node_id '', node_name '', event_type 'event', description '', day 1, created_at. idx(playthrough_id, day DESC, created_at DESC).
- schema_migrations: filename PK, applied_at (migrate.py).

## 3. BUSINESS INVARIANTS (code-enforced)
- Stats: Health clamped 0..MaxHealth (baseline 100), Mana 0..MaxMana (baseline 50), MaxHealth/MaxMana 1..999, other stats 0..999 — enforced in state_applier._stat_cap + update_playthrough_character_stat + frontend clampStat. LEVEL SYSTEM: raising MaxHealth/MaxMana raises caps everywhere automatically.
- Stackables (consumable/material) must stack: grant stacks by (name,type); applier bumps existing rows; dedupe_stackables merges duplicates on every inventory read (quantity ≤9999).
- Equipment: one per (character,slot); swap math; equipped items weigh nothing; capacity 5+5×level; quest undroppable.
- World: names unique per (playthrough,node_type,LOWER(name)); descriptions fill-only-when-empty; LOCATION_UPDATE always registers a settlement node; relationship/power/wealth clamped.
- Isolation: playthrough endpoints check user_id; story lists filter creator_id/is_public; legacy rows never leak (base_only + per-playthrough seeding).

## 4. METHOD → TABLE MATRIX
database.py: Auth/Users methods → users/auth_tokens · ensure_session/add_message/get_last_session_message → chat_* · create_story/set_story_visibility/get_story/list_stories_for_user(creator_id+creator_name+played_count)/list_all_stories/update_story_time/update_story_location → stories(+users join) · add_story_character/get_story_characters/update_character_stat → story_characters · add_story_message/get_story_messages → story_messages · notes CRUD → story_notes · playthrough methods (get_active/get/complete/create/list/update_time/update_location/get_characters/get_messages/add_message) → playthroughs/playthrough_characters/story_messages · upsert_playthrough_location/get_playthrough_locations/get_playthrough_map → locations(+playthroughs.metadata) · stat/ability/inventory mirror → playthrough_characters.metadata · inventory/equipment/backpack methods → playthrough_items/equipment/backpacks · get_full_playthrough_state (batch) · get_recent_messages_for_context → story_messages · get_memory_summary/get_lorebook/get_and_clear_nudge → playthroughs.metadata · get_world_nodes/bulk_insert_world_nodes/get_node_context_for_location → world_nodes.
db_ext.py: set_story_art/set_story_banner/get_all_story_art/update_story_fields → stories · set_character_image/set_character_image_by_id/get_cast_with_images → story_characters · find_stackable_item/bump_item_quantity/dedupe_stackables → playthrough_items(+equipment cleanup) · get_world_nodes_full/ensure_world_node/update_world_node_state → world_nodes · record_world_event/get_recent_world_events → world_events(+world_nodes lookup) · set_memory_summary → playthroughs.metadata.
core/auth.py: get_user_by_token → auth_tokens JOIN users. migrate.py → schema_migrations + migrations/*.sql.

## 5. MIGRATION LEDGER
0001 core (users+legacy seed, tokens, chat, stories, characters, messages, notes) · 0002 playthroughs + story_messages.playthrough_id + backfill · 0003 hardening (NOT NULL/defaults) · 0004 locations_hud · 0005 robustness (indexes, CHECKs, triggers, unique location) · 0006 items_equipment · 0007 visibility · 0009 map_completion (visit_count/last_visited_at) · 0010 location_upsert_index · 0011_memory_and_lore (dormant columns) · 0011_story_art (cover/banner/character image) · 0012 world_nodes · 0013 world_state + world_events. (0008 absent — see BACKEND B-6. Two 0011s apply; ledger tracks filenames.)

## 6. DISCREPANCY LEDGER (append-only)
- D-1 — memory/lore/nudge live in metadata JSONB; dedicated columns dormant. OPEN (user decision).
- D-2 — 0008_story_indexes.sql missing from repo. OPEN.
- D-3 — world_nodes unique key includes node_type but update_world_node_state upserts by name across types. ACCEPTED (documented behavior).
- D-4 — quick-chat sessions UI is localStorage-only (DB writes exist). OPEN.
