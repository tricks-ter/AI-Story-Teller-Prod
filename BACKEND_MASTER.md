# BACKEND MASTER CONTRACT — InkMind
> Verified against commit f32ebcc + the FE-BUG-1 / A-3-B1 fix sprint.
> GOVERNANCE: APPEND-ONLY. Never remove entries or restructure until the user
> explicitly orders a refactor. Keep FRONTEND_MASTER.md §6 and DATABASE_MASTER.md §4 consistent.

## 1. STACK & DEPLOY
FastAPI 0.115.5 on Vercel serverless · single api/main.py · APIRouter(prefix="/api") · app.include_router(router) at file end · app version 7.4.0. vercel.json: buildCommand cd frontend && npm install && npm run build; rewrites /api/(.*) → /api/main.py, /(.*) → /index.html. Migrations DEPLOY-TIME ONLY (migrate.yml → api/migrate.py, schema_migrations ledger). Runtime init_tables() = connection check only. CORS open (no per-user rate limit yet).

## 2. MODULE ROLES
main.py (routes/SSE/guards) · database.py (Database class, singleton db, ~60 methods) · db_ext.py (additive: art, story fields, world state/events, stackables, memory) · core/auth.py (PBKDF2 + tokens) · core/prompt_assembler.py · core/state_resolver.py · core/state_applier.py · core/resilience.py · migrate.py · tests/ (resolver, resilience, main helpers).

## 3. GUARDS
require_user (all routes, 401) · check_story_access (foreign/private 403; LEGACY_USER_ID bypass) · require_story_owner (notes, visibility) · db_ext.can_manage_story (PATCH story, art routes: owner OR legacy-claim) · require_own_playthrough · ensure_playthrough · _resolve_player_char · _recent_duplicate (90s idempotency) · REASON_TEXT (human errors).

## 4. REQUEST MODELS
MessageItem · ChatRequest · StoryContinueRequest · StoryCreateRequest · StoryUpdateRequest · AuthRequest · ItemActionRequest · NoteCreateRequest · VisibilityRequest · ArtUpdateRequest{image,banner,kind,data_url} · CharArtRequest{data_url}.

## 5. ROUTE TABLE (guard · db calls · tables · frontend caller)
- GET /health · SELECT 1 · App boot
- POST /auth/signup|login|logout · GET /auth/me · users, auth_tokens · AuthPage/App
- GET /stories?scope=all|mine · db.list_all_stories / list_stories_for_user (both return creator_id+creator_name+played_count) · stories,users,story_characters,playthroughs · StoryLibrary
- GET /stories/art (BEFORE /stories/{id}) · db_ext.get_all_story_art · stories · StoryLibrary
- GET /art/stories?ids= (A-3/B-1) · db_ext.get_all_story_art filtered · stories · utils/art.js
- GET /stories/{id} · db.get_story + get_story_characters + image merge from db_ext.get_cast_with_images (try/fallback) · stories,story_characters · StoryDetails
- GET /stories/{id}/cast (A-3/B-1) · db_ext.get_cast_with_images (id,name,role,background,is_player,image) · story_characters · utils/art.js
- PATCH /stories/{id} · db_ext.can_manage_story + update_story_fields (title≤120, genre≤60, premise≤2000, cover/banner ≤900KB) · stories · StoryCreator edit
- POST /stories/{id}/art · can_manage_story; accepts {image,banner} AND {kind,data_url} (kind=banner → banner_image) · stories · StoryLibrary + utils/art.js
- POST /stories/{id}/characters/{char_id}/art (A-3/B-1) · can_manage_story + db_ext.set_character_image_by_id (story-scoped, 404 if char missing) · story_characters · utils/art.js
- POST /stories · create story + character (stats seed Health/MaxHealth=100, Mana/MaxMana=50) + intro 'legacy' message · StoryCreator
- POST /stories/{id}/play · ensure_playthrough + ensure_playthrough_inventory · App.handleStartJourney
- POST /stories/{id}/continue (SSE) · pipeline §6 · api.streamStory
- GET /stories/{id}/messages · base_only → playthrough_id='legacy' · App/art.js
- notes CRUD + visibility · require_story_owner · story_notes/stories (⚠ no frontend caller currently)
- GET /playthroughs · list_playthroughs_for_user · StoryLibrary History
- GET /playthroughs/{id}/messages|map|inventory · O · inventory runs db_ext.dedupe_stackables first · syncQueue/api.js
- GET /playthroughs/{id}/world-nodes|world-events · db_ext.get_world_nodes_full / get_recent_world_events · WorldCodex/syncQueue
- POST /playthroughs/{id}/compress · >50 msgs → Pulse (glm-4.5-flash) summarize ≤250 words → db_ext.set_memory_summary (metadata.memory_summary) · syncQueue
- POST /playthroughs/{id}/equip|unequip|use|drop|complete · db item methods / complete_playthrough · HUD_ACTION/App

## 6. STORY TURN PIPELINE (continue_story)
auth+access → ensure_playthrough → dedupe-guard user msg → PromptAssembler (§7) → ZAI stream via call_with_retry(3) → SSE thinking/content → resolve_state → apply_state_updates → save clean narration → SSE state_update{clean_content,applied,rejected,day,time_of_day,status} → done. Errors: SSE error{code,retry_after,message}.

## 7. PROMPT ORDER (prompt_assembler.py)
SYSTEM + TAG CONTRACT → STATE TAG RULES (incl. HP/MP caps + delta-only damage) → LIVING WORLD RULES → PLAYER AGENCY → STYLE → WORLD STATE → LOCAL ENVIRONMENT (node + ≤20 children) → WORLD CODEX (≤30 nodes w/ state) → RECENT WORLD EVENTS (≤8) → Active Characters → Known Locations → STORY MEMORY (summary, lorebook ≤15, recent msgs, nudge) → DIRECTOR'S NOTES → PLAYER ACTION.

## 8. TAG PROTOCOL (resolver → applier)
TIME_UPDATE · STAT_UPDATE (is_delta when "= ±N" or space form; applier adds to current; cap via _stat_cap: Health→MaxHealth default 100, Mana→MaxMana default 50, else 999; db clamps 0..cap) · LOCATION_UPDATE (upsert locations + set current_location + db_ext.ensure_world_node settlement) · ITEM_UPDATE ± (stackables bump quantity via find_stackable_item/bump_item_quantity; capacity gate) · ABILITY_UPDATE · BAG_UPDATE (level 1..20) · WORLD_STATE_UPDATE (upsert; kind aliases kingdom→region, family/house→faction, building/shop/inn/tavern/temple/market→location, city/town/village→settlement; parent resolution; deltas + clamps rel −100..100, power 0..100, wealth 0..9,999,999; desc fill-only-empty) · WORLD_EVENT (ledger w/ current day) · SAGA_END (complete_playthrough).

## 9. RESILIENCE
RETRYABLE {429,500,502,503,504} · CircuitBreaker threshold 5 → open 30s (singleton BREAKER) · backoff base 0.8 ×2^attempt cap 8.0 full jitter, honors Retry-After (0.5–30s) · friendly_upstream human text · frontend mirrors one retry (api.js runStream).

## 10. DB_EXT FUNCTION INDEX
set_story_art · set_story_banner · get_all_story_art · set_character_image (by name) · set_character_image_by_id (by id, story-scoped) · get_cast_with_images (id,name,role,background,is_player,image) · can_manage_story · update_story_fields · find_stackable_item · bump_item_quantity · dedupe_stackables · get_world_nodes_full · ensure_world_node · update_world_node_state · record_world_event · get_recent_world_events · set_memory_summary.

## 11. DISCREPANCY LEDGER (append-only)
- B-1/A-3 — art.js endpoints missing. RESOLVED 2026-08-13 (§5: /art/stories, /cast, /characters/{cid}/art, ArtUpdateRequest extended).
- FE-BUG-1 backend half — applier now caps Health/Mana by MaxHealth/MaxMana (_stat_cap). RESOLVED 2026-08-13.
- B-2 — playthroughs.memory_summary/lorebook/active_nudge COLUMNS exist (0011_memory_and_lore) but code uses metadata JSONB — columns dormant. OPEN (user decision).
- B-4 — notes + visibility routes have no frontend caller. OPEN.
- B-5 — no per-user rate limit; CORS open. OPEN.
- B-6 — 0008_story_indexes.sql absent from repo (old docs reference it). OPEN (verify production indexes if plans degrade).
