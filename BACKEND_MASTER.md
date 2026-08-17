# BACKEND MASTER CONTRACT — InkMind
> Verified against commit f32ebcc (branch main, 2026-08-13).
>
> GOVERNANCE (immutable): (1) APPEND-ONLY — never remove entries or restructure unless the user
> explicitly orders it; when routes/methods change, update the matching row in the same commit.
> (2) Keep FRONTEND_MASTER.md §8 and DATABASE_MASTER.md §5 consistent with any change here.
> (3) ⚠ DISCREPANCY = verified cross-layer mismatch.
>
> HOW TO USE: find the route in §5 (it names its guard, db methods, tables, and frontend caller).
> For AI-turn internals read §6–§9. Never add runtime migrations (§14).

## 1. STACK & DEPLOYMENT
- FastAPI 0.115.5 (Vercel serverless), single app file api/main.py, APIRouter(prefix="/api"), mounted via app.include_router(router) at file end. app version "7.3.0".
- vercel.json: buildCommand "cd frontend && npm install && npm run build", outputDirectory frontend/dist; rewrites /api/(.*) → /api/main.py, /(.*) → /index.html.
- DB: PostgreSQL (psycopg2-binary 2.9.9) — single reused connection + threading.RLock + one retry (Database._with_conn). DATABASE_URL + sslmode=require.
- AI: Z.AI SDK (zai.ZaiClient 0.2.3). Models: glm-4.7-flash (InkMind Nova, default), glm-4.5-flash (Pulse, used by /compress).
- Migrations: DEPLOY-TIME ONLY via .github/workflows/migrate.yml → api/migrate.py (GitHub secret DATABASE_URL, on push to main + dispatch). Runtime init_tables() = connection check only.
- CI: .github/workflows/tests.yml → pytest api/tests -q. Alt hosts: render.yaml, start.sh.
- CORS: allow_origins=["*"] (open by design; no per-user rate limit yet).

## 2. MODULE MAP
| File | Role |
|---|---|
| api/main.py | ALL routes, SSE generators, guards, idempotency, Pydantic models |
| api/database.py | Database class (~60 methods) + module singleton db |
| api/db_ext.py | Additive helpers: story art/fields, world state/events, stackables, memory |
| api/core/auth.py | PBKDF2 hashing + tokens |
| api/core/prompt_assembler.py | Builds the full AI prompt |
| api/core/state_resolver.py | Parses [TAG]s out of AI prose |
| api/core/state_applier.py | Applies parsed tags to the world |
| api/core/resilience.py | Retry/backoff/circuit breaker for upstream AI |
| api/migrate.py | Migration runner (schema_migrations ledger) |
| api/tests/ | pytest: resolver, resilience, main helpers |

## 3. PYDANTIC REQUEST MODELS (main.py)
MessageItem{role,content} · ChatRequest{session_id,messages[],model,max_tokens 256–8192,temperature 0–1.5,enable_thinking,client_telemetry} · StoryContinueRequest{user_action,model,max_tokens,temperature,enable_thinking,client_telemetry} · StoryCreateRequest{title,genre,premise,characterName,characterRole,characterBackground,isPublic,client_telemetry} · StoryUpdateRequest{title?,genre?,premise?,cover_image?,banner_image?} · AuthRequest{username,password,remember_me,client_telemetry} · ItemActionRequest{item_id,character_id?} · NoteCreateRequest{content,priority} · VisibilityRequest{is_public} · ArtUpdateRequest{image,banner}.

## 4. GUARDS & HELPERS (main.py)
| Helper | Rule |
|---|---|
| get_auth_user | Bearer token → users row via core.auth.get_user_by_token (expires_at > NOW) |
| require_user | 401 "Login required" if no valid token — used by EVERY route |
| check_story_access | 403 if foreign owner (≠ user & ≠ LEGACY_USER_ID) or private non-owned |
| require_story_owner | strict owner — notes & visibility routes |
| db_ext.can_manage_story | owner OR creator_id in (None,'','legacy-system') — PATCH & art routes |
| require_own_playthrough | playthrough.user_id must equal user.id |
| ensure_playthrough | get active playthrough or create |
| _resolve_player_char | requested char_id or player char |
| _recent_duplicate(last_row, content, 90s) | idempotent retry guard for user messages |
| REASON_TEXT | human-readable item-action failure messages |

## 5. ROUTE TABLE (complete)
Guard key: U=require_user, O=require_own_playthrough, S=check_story_access, W=require_story_owner, M=can_manage_story(owner-or-legacy).
| Method + Path | Handler | Guard | DB calls | Tables | Frontend caller |
|---|---|---|---|---|---|
| GET /api/health | health | — | SELECT 1 | — | App boot |
| POST /api/auth/signup | signup | — | db.create_user_with_token | users, auth_tokens | AuthPage |
| POST /api/auth/login | login | — | db.purge_expired_tokens, get_user_by_username, touch_user_login, add_auth_token | users, auth_tokens | AuthPage |
| POST /api/auth/logout | logout | — | db.delete_auth_token | auth_tokens | App |
| GET /api/auth/me | me | U | get_user_by_token | auth_tokens, users | App boot |
| GET /api/stories?scope=all\|mine | list_stories | U | db.list_all_stories / list_stories_for_user | stories, users, story_characters, playthroughs | StoryLibrary |
| GET /api/stories/art | stories_art (declared BEFORE /stories/{id}) | U | db_ext.get_all_story_art | stories | StoryLibrary |
| GET /api/stories/{id} | get_story_detail | U+S | db.get_story, get_story_characters | stories, story_characters | StoryDetails |
| PATCH /api/stories/{id} | update_story | U+M | db.get_story, db_ext.update_story_fields (title/genre/premise/cover/banner, ≤limits) | stories | App.handleUpdateStory |
| POST /api/stories/{id}/art | set_story_art | U+M | db_ext.set_story_art / set_story_banner; validates data:image + ≤900KB | stories | StoryLibrary upload |
| GET /api/stories/{id}/messages | get_story_messages | U+S | db.get_story_messages(base_only → playthrough_id='legacy') | story_messages | App seed, art.js fetchPrologue |
| GET /api/stories/{id}/notes | get_story_notes | U+S | db.list_story_notes_full | story_notes | ⚠ no current UI caller |
| POST /api/stories/{id}/notes | create_story_note | U+W | db.add_story_note | story_notes | ⚠ no current UI caller |
| POST /api/stories/{id}/notes/{nid}/toggle | toggle_story_note | U+W | db.toggle_story_note | story_notes | ⚠ no current UI caller |
| DELETE /api/stories/{id}/notes/{nid} | delete_story_note | U+W | db.delete_story_note | story_notes | ⚠ no current UI caller |
| POST /api/stories/{id}/visibility | set_visibility | U+W | db.set_story_visibility | stories | ⚠ no current UI caller |
| POST /api/stories/{id}/play | play_story | U+S | db.get_story, ensure_playthrough→create_playthrough, db.ensure_playthrough_inventory | playthroughs, playthrough_characters, story_messages, playthrough_backpacks, playthrough_items | App.handleStartJourney |
| POST /api/stories | create_new_story | U | db.create_story, add_story_character, add_story_message(intro,'legacy') | stories, story_characters, story_messages | App.handleStartStory |
| POST /api/stories/{id}/continue | continue_story (SSE) | U+S | see §6 | many | api.streamStory |
| GET /api/playthroughs | list_playthroughs | U | db.list_playthroughs_for_user | playthroughs, stories, playthrough_characters, story_messages | StoryLibrary History |
| GET /api/playthroughs/{id}/messages | get_playthrough_messages | U+O | db.get_playthrough_messages (limit ≤200) | story_messages | App seed, syncQueue |
| GET /api/playthroughs/{id}/map | get_map | U+O | db.get_playthrough_map; marks is_current from playthroughs.metadata.current_location | locations, playthroughs | api.fetchMap |
| GET /api/playthroughs/{id}/inventory | get_inventory | U+O | db_ext.dedupe_stackables → db.ensure_playthrough_inventory, list_playthrough_items, list_playthrough_equipment, list_playthrough_backpacks(+capacity/used), compute_equipped_bonuses, get_playthrough_characters(abilities) | playthrough_items/equipment/backpacks/characters | api.fetchInventory |
| GET /api/playthroughs/{id}/world-nodes | get_world_nodes_route | U+O | db_ext.get_world_nodes_full | world_nodes | WorldCodex, syncQueue |
| GET /api/playthroughs/{id}/world-events | get_world_events_route | U+O | db_ext.get_recent_world_events (≤50) | world_events | WorldCodex |
| POST /api/playthroughs/{id}/compress | compress_memory | U+O | db.get_playthrough_messages(200); if >50 → Pulse summarize → db_ext.set_memory_summary | story_messages, playthroughs.metadata | syncQueue COMPRESS_MEMORY |
| POST /api/playthroughs/{id}/equip | equip_item | U+O | db.equip_item | playthrough_items, playthrough_equipment, playthrough_characters | syncQueue HUD_ACTION |
| POST /api/playthroughs/{id}/unequip | unequip_item | U+O | db.unequip_item | playthrough_items, playthrough_equipment | syncQueue HUD_ACTION |
| POST /api/playthroughs/{id}/use | use_item | U+O | db.use_item | playthrough_items, playthrough_equipment | syncQueue HUD_ACTION |
| POST /api/playthroughs/{id}/drop | drop_item | U+O | db.drop_item | playthrough_items, playthrough_equipment | syncQueue HUD_ACTION |
| POST /api/playthroughs/{id}/complete | complete_playthrough | U+O | db.complete_playthrough | playthroughs | App.handleEndJourney |
| POST /api/chat/stream | chat_stream (SSE) | optional U | db.ensure_session, add_message (dedupe guard) | chat_sessions, chat_messages | api.streamChat |

## 6. STORY TURN PIPELINE (continue_story)
1. Auth + check_story_access; ensure_playthrough; telemetry.
2. Insert user action into story_messages unless _recent_duplicate (90s).
3. PromptAssembler(pid).assemble_full_prompt(action) (§7).
4. Stream ZAI chat.completions (stream=True, thinking enabled/disabled) through call_with_retry(max_attempts=3); emit SSE thinking/content chunks. Upstream errors → SSE error{code,retry_after,message} + done.
5. On stream end: resolve_state(full) → apply_state_updates(pid, updates) (§8–§9).
6. Save clean narration (message_type='narration').
7. Emit state_update{clean_content, updates:applied, rejected, day, time_of_day, status} then done.

## 7. PROMPT ASSEMBLER ORDER (core/prompt_assembler.py)
PromptAssembler(playthrough_id, max_chars=40000) loads pt, story, db.get_full_playthrough_state (batch: characters/items/equipment/backpacks), get_recent_messages_for_context (newest-first until 60% of max_chars), get_memory_summary, get_lorebook, get_and_clear_nudge, get_story_notes(active).
Prompt order: [SYSTEM INSTRUCTIONS + TAG CONTRACT] → [STATE TAG RULES] → [LIVING WORLD RULES] → [PLAYER AGENCY RULES] → [STYLE RULES] → [WORLD STATE] (story/day/time/current location) → [LOCAL ENVIRONMENT] (db.get_node_context_for_location: node + ≤20 children) → [WORLD CODEX] (db_ext.get_world_nodes_full, ≤30 entries with status/alive/relationship/power/wealth/allegiance) → [RECENT WORLD EVENTS] (≤8) → Active Characters (stats/abilities/carried ×qty/equipped/backpack load) → Known Locations (get_playthrough_map) → [STORY MEMORY] (memory summary, lorebook ≤15, recent messages, nudge) → [DIRECTOR'S NOTES] → [PLAYER'S CURRENT ACTION].

## 8. TAG PROTOCOL & RESOLVER (core/state_resolver.py)
Regex strips tags; payload parsed per type. is_delta for STAT_UPDATE: the "= -10"/"= +5" form is delta when the right side starts with + or -; the space form "Char.Stat -10" is always delta.
| Tag | Parsed result | Notes |
|---|---|---|
| TIME_UPDATE: Day X, TimeOfDay | day, time_of_day | TimeOfDay ∈ Morning/Afternoon/Evening/Night |
| STAT_UPDATE: Char.Stat = N | value, is_delta | signed = delta |
| LOCATION_UPDATE: Name \| desc= | location, description | |
| ITEM_UPDATE: Char + Item \| type,slot,rarity,level,weight,bonus.X,desc | add, item, attrs | typed; bonuses dict |
| ITEM_UPDATE: Char - Item | add=False | |
| ABILITY_UPDATE: Char + Name \| desc | add, ability, description | |
| BAG_UPDATE: Char level N | character, level | |
| WORLD_STATE_UPDATE: Name \| kind,parent,status,relationship,power,wealth,is_alive,allegiance,desc | name + fields | is_alive parsed to bool |
| WORLD_EVENT: Name \| type,desc | name, event_type(default 'event'), description | |
| SAGA_END | {} | |
_parse_attrs lowercases keys; desc|description → description; bonus.X → bonuses.

## 9. APPLIER BEHAVIOR (core/state_applier.py)
| Update | Behavior | Tables |
|---|---|---|
| TIME_UPDATE | update_playthrough_time (day ≥1) | playthroughs |
| STAT_UPDATE | if is_delta: current+value; clamp 0..999 | playthrough_characters.metadata.stats |
| LOCATION_UPDATE | upsert_playthrough_location (ON CONFLICT LOWER(name): visit_count+1, fill empty desc) + set metadata.current_location; ALSO db_ext.ensure_world_node(kind='settlement') | locations, playthroughs, world_nodes |
| ITEM_UPDATE add | if stackable (consumable/material) already carried → bump quantity (anti-duplicate); else grant with capacity check | playthrough_items, equipment, backpacks |
| ITEM_UPDATE remove | consume (decrement/delete + equipment cleanup) | playthrough_items/equipment |
| ABILITY_UPDATE | add/update/remove in metadata.abilities | playthrough_characters |
| BAG_UPDATE | backpack level 1..20 | playthrough_backpacks |
| WORLD_STATE_UPDATE | db_ext.update_world_node_state: upsert node (kind aliases kingdom→region, family/house→faction, building/shop/inn/tavern/temple/market→location, city/town/village→settlement), resolve/create parent, delta math + clamps (relationship −100..100, power 0..100, wealth 0..9,999,999), desc fills only when empty | world_nodes |
| WORLD_EVENT | db_ext.record_world_event (day from playthrough) | world_events |
| SAGA_END | complete_playthrough | playthroughs |
Returns {applied, rejected[{...reason}]} — rejection reasons surface in the UI notice.

## 10. RESILIENCE (core/resilience.py)
RETRYABLE_STATUSES {429,500,502,503,504}; CircuitBreaker (threshold 5 consecutive 429s → open 30s; singleton BREAKER); extract_status probes exception attrs/text; extract_retry_after (0.5–30s); backoff_delay = Retry-After+jitter or base 0.8 × 2^attempt capped 8.0 with full jitter; call_with_retry(fn, max_attempts, label); friendly_upstream human messages. Frontend mirrors with one transport retry (api.js runStream).

## 11. DATABASE METHODS INDEX (api/database.py — class Database, singleton db)
- Auth/Users: create_user_with_token, add_auth_token, delete_auth_token, purge_expired_tokens, touch_user_login, create_user, get_user_by_username, get_user_by_id, update_user_metadata.
- Quick chat: ensure_session, add_message, get_last_session_message.
- Stories: create_story (is_public try/fallback), set_story_visibility, add_story_character, add_story_message, list_stories_for_user (incl. creator_id+creator_name+played_count), list_all_stories (public OR own; creator_name join; is_public fallback), get_story (SELECT *), get_story_characters, get_story_messages (base_only → playthrough_id='legacy').
- Notes: get_story_notes (active, priority DESC, ≤10 for prompt), list_story_notes_full (≤50), add_story_note, toggle_story_note, delete_story_note.
- Playthroughs: get_active_playthrough, get_playthrough, complete_playthrough, create_playthrough (seeds characters from story_characters, copies 'legacy' messages, creates backpacks), get_playthrough_characters, get_playthrough_messages, get_last_playthrough_message, add_playthrough_message, list_playthroughs_for_user.
- World state: update_playthrough_time, update_playthrough_location, upsert_playthrough_location (SAVEPOINT + ON CONFLICT + manual fallback), get_playthrough_locations, get_playthrough_map, update_playthrough_character_stat (clamp), update_playthrough_character_ability, update_playthrough_character_inventory, _sync_inventory_mirror.
- Inventory: ensure_playthrough_inventory (backpacks + seed mirror items + default descriptions), get_backpack_for_character, list_playthrough_backpacks, backpack_used_capacity (excludes equipped), list_playthrough_items, list_carried_items_for_character, list_playthrough_equipment, list_equipment_for_character, compute_equipped_bonuses, set_playthrough_backpack_level, grant_playthrough_item (stackables stack; capacity gate), consume_playthrough_item, use_item (consumable only), drop_item (quest locked), equip_item (swap math + capacity), unequip_item (capacity gate). backpack_capacity(level)=5+5*level.
- Legacy story-scoped: update_story_time, update_story_location, update_character_stat.
- Phase 6: get_full_playthrough_state (batch, kills N+1), get_recent_messages_for_context (char budget), get_memory_summary (metadata.memory_summary), get_lorebook (metadata.lorebook), get_and_clear_nudge (metadata.active_nudge pop).
- Phase 7: get_world_nodes (optionally by parent), bulk_insert_world_nodes (ON CONFLICT DO NOTHING), get_node_context_for_location (node + ≤20 children).

## 12. DB_EXT FUNCTION INDEX (api/db_ext.py)
set_story_art, set_story_banner, get_all_story_art ({id:{cover,banner}}), set_character_image, get_cast_with_images, can_manage_story, update_story_fields (whitelist title/genre/premise/cover_image/banner_image), find_stackable_item, bump_item_quantity (≤9999), dedupe_stackables (merge dup consumable/material rows; runs on every GET inventory), get_world_nodes_full (state columns; fallback to db.get_world_nodes), ensure_world_node (create-if-missing, fills empty desc only), update_world_node_state (§9), record_world_event, get_recent_world_events, set_memory_summary (playthroughs.metadata.memory_summary).

## 13. CORE/AUTH (api/core/auth.py)
hash_password (PBKDF2-HMAC-SHA256, 100k iters, salt$hex), verify_password (compare_digest), make_token (secrets.token_urlsafe(32); 30 days remember / 12h session), get_user_by_token (JOIN users, expires_at > NOW).

## 14. MIGRATIONS (api/migrate.py)
Creates schema_migrations(filename PK, applied_at); applies migrations/*.sql in sorted filename order not yet in ledger; per-file transaction, stop on first failure. NEVER add runtime DDL. Ledger = filenames (two files share number 0011 — allowed because tracking is by filename).

## 15. TESTS (api/tests/)
test_main_helpers (_recent_duplicate window/role/content), test_resilience (backoff bounds, retry-after, status extraction, breaker open/reset, retry success/non-retryable), test_state_resolver (legacy tags incl. delta/attrs/strip). ⚠ no tests yet for WORLD_* tags, db_ext, or routes.

## 16. KNOWN DISCREPANCIES (resolve; don't delete until fixed)
- B-1: frontend utils/art.js expects /api/art/stories?ids=, /api/stories/{id}/cast, /api/stories/{id}/characters/{cid}/art and body {kind,data_url} — none exist; current contract is POST /api/stories/{id}/art {image,banner}. Implement or delete art.js (paired with FRONTEND A-3).
- B-2: playthroughs.memory_summary/lorebook/active_nudge COLUMNS exist (0011_memory_and_lore) but code uses playthroughs.metadata JSONB instead — columns dormant. Pick one storage and migrate.
- B-3: bulk_insert_world_nodes uses unique (playthrough_id, node_type, LOWER(name)), but db_ext.update_world_node_state upserts by NAME ONLY across types — two types with the same name can diverge. Acceptable for now; document if it bites.
- B-4: notes + visibility routes have no frontend UI callers currently (director's notes UI lost in a past rewrite). Re-wire when requested.
- B-5: no per-user rate limit; CORS open. (Roadmap Phase 8.)
- B-6: 0008_story_indexes.sql referenced by old docs is ABSENT from repo — if never applied, creator/updated indexes on stories may be missing (low risk; see DATABASE D-2).

## 17. MAINTENANCE RULES
- New route → add row to §5 (guard + db calls + tables + frontend caller) and update FRONTEND_MASTER §8.
- New db method → §11/§12 + DATABASE_MASTER §5 matrix.
- New AI tag → resolver §8 row + applier §9 row + prompt contract (assembler) + FRONTEND state_update handling.
- New table/column → DATABASE_MASTER §3 + new numbered migration.
