# BACKEND MASTER CONTRACT — InkMind
> Verified vs commit f32ebcc + "comprehensive forge + masters" commit. APPEND-ONLY.
> Keep FRONTEND_MASTER §6 and DATABASE_MASTER §4 consistent with any change.

## 1. STACK & DEPLOY
FastAPI 0.115.5 on Vercel serverless · api/main.py · APIRouter(prefix="/api") mounted at file end · app v7.5.0. vercel.json: /api/(.*) → /api/main.py; /(.*) → /index.html. Migrations DEPLOY-TIME ONLY (migrate.yml → api/migrate.py, schema_migrations ledger); runtime init_tables() = connection check. CORS open. AI: zai-sdk; glm-4.7-flash default, glm-4.5-flash for /compress.

## 2. MODULES
main.py (routes/SSE/guards/models) · database.py (Database class + db singleton) · db_ext.py (additive: art, story fields/metadata, world state/events, stackables, memory) · core/auth.py (PBKDF2 100k, tokens 30d/12h) · core/prompt_assembler.py · core/state_resolver.py · core/state_applier.py · core/resilience.py (breaker 5×429→30s, backoff 0.8×2^n cap 8 jitter) · migrate.py · tests/.

## 3. GUARDS
require_user (all routes) · check_story_access (foreign/private 403; legacy bypass) · require_story_owner (notes/visibility) · db_ext.can_manage_story (owner OR legacy-claim: PATCH story, art routes) · require_own_playthrough · ensure_playthrough · _resolve_player_char · _recent_duplicate (90s) · _valid_data_url (data:image ≤900KB).

## 4. MODELS
ChatRequest · StoryContinueRequest · StoryCreateRequest{title,genre,premise,characterName/Role/Background,isPublic,coverImage,bannerImage,characterImage,starterLocation,tone} · StoryUpdateRequest{title,genre,premise,coverImage,bannerImage,isPublic,starterLocation,tone,characterId,characterName,characterRole,characterBackground,characterImage} · AuthRequest · ItemActionRequest · NoteCreateRequest · VisibilityRequest · ArtUpdateRequest{image,banner,kind,data_url} · CharArtRequest{data_url} · CharacterUpdateRequest{name,role,background}.

## 5. ROUTE TABLE (guard · db calls · tables · caller)
GET /health · SELECT 1 · App
POST /auth/signup|login|logout · GET /auth/me · users, auth_tokens · AuthPage/App
GET /stories?scope · list_all_stories / list_stories_for_user (creator_id+creator_name+played_count) · StoryLibrary
GET /stories/art (BEFORE /stories/{id}) · db_ext.get_all_story_art · StoryLibrary
GET /art/stories?ids= · filtered art map · art.js
GET /playthroughs · list_playthroughs_for_user · StoryLibrary History
GET /playthroughs/{id}/messages|map · O · App/StoryMap/syncQueue
GET /playthroughs/{id}/inventory · O · dedupe_stackables → ensure → list items/equipment/backpacks + bonuses + abilities · InventoryPanel/syncQueue
GET /playthroughs/{id}/world-nodes|world-events · O · db_ext · WorldCodex/syncQueue
POST /playthroughs/{id}/compress · O · >50 msgs → Pulse summarize → set_memory_summary · syncQueue
POST /playthroughs/{id}/equip|unequip|use|drop · O · db item methods · HUD_ACTION
POST /playthroughs/{id}/complete · O · complete_playthrough · App
GET /stories/{id} · U+S · get_story + get_story_characters + image merge via get_cast_with_images · StoryDetails/art.js
GET /stories/{id}/cast · U+S · get_cast_with_images · art.js
PATCH /stories/{id} · M · update_story_fields + set_story_visibility + set_story_metadata_keys + update_story_character + set_character_image_by_id · StoryCreator edit
PATCH /stories/{id}/characters/{cid} · M · update_story_character · (direct clients)
POST /stories/{id}/art · M · set_story_art/set_story_banner; accepts {image,banner} AND {kind,data_url} · StoryLibrary/art.js
POST /stories/{id}/characters/{cid}/art · M · set_character_image_by_id · art.js
GET/POST/DELETE /stories/{id}/notes… · S/W · story_notes · (no current UI caller)
POST /stories/{id}/visibility · W · set_story_visibility · (no current UI caller)
POST /stories/{id}/play · U+S · ensure_playthrough + ensure_playthrough_inventory · App
POST /stories · U · create_story(meta starter_location/tone) + add_story_character(stats Health/MaxHealth 100, Mana/MaxMana 50) + intro 'legacy' msg + art setters · StoryCreator
POST /stories/{id}/continue · U+S · pipeline §6 · streamStory
POST /chat/stream · optional U · ensure_session/add_message · streamChat

## 6. STORY TURN PIPELINE
auth+access → ensure_playthrough → dedupe user msg → PromptAssembler → ZAI stream (call_with_retry 3) → SSE thinking/content → resolve_state → apply_state_updates → save narration → SSE state_update{clean_content, applied, rejected, day, time_of_day, status} → done. Errors: SSE error{code,retry_after,message}.

## 7. TAG PROTOCOL & BEHAVIOR
Resolver: TIME, STAT(=±N or space form ⇒ is_delta), LOCATION(desc), ITEM ±(attrs incl bonus./desc), ABILITY ±, BAG, WORLD_STATE_UPDATE(kind/parent/status/relationship/power/wealth/is_alive/allegiance/desc), WORLD_EVENT(type/desc), SAGA_END.
Applier: STAT delta adds to current, clamp 0..999 (backend) — frontend clamps to MaxHealth/MaxMana (see FRONTEND §5, D-5); LOCATION upsert + ensure_world_node(settlement); ITEM stackables bump qty else grant w/ capacity; WORLD_STATE upsert w/ parent auto-create + clamps (rel ±100, power 0..100, wealth ≤9,999,999); WORLD_EVENT ledger w/ current day; SAGA_END completes.
PromptAssembler order: SYSTEM+tags+rules(living world/agency/style) → WORLD STATE(+tone/starter from story metadata via §5 GET) → LOCAL ENVIRONMENT(node+children) → WORLD CODEX(≤30) → RECENT EVENTS(≤8) → characters(stats/abilities/carried/equipped/backpack) → known locations → MEMORY(summary/lorebook/recent/nudge) → DIRECTOR'S NOTES → ACTION.

## 8. DB METHOD INDEX (database.py)
auth/users · quick chat · stories(create/list/get/characters/messages/visibility) · notes CRUD · playthroughs(get/create/complete/list/messages) · state(time/location upsert/stat/ability/inventory mirror) · inventory(ensure/list/capacity/grant/consume/use/drop/equip/unequip/bonuses/backpack level) · legacy story-scoped · Phase6(get_full_playthrough_state, get_recent_messages_for_context, get_memory_summary, get_lorebook, get_and_clear_nudge) · Phase7(get_world_nodes, bulk_insert_world_nodes, get_node_context_for_location).

## 9. DB_EXT INDEX
set_story_art · set_story_banner · get_all_story_art · set_character_image · set_character_image_by_id · get_cast_with_images(id,name,role,background,is_player,image) · update_story_character · set_story_metadata_keys · can_manage_story · update_story_fields · find_stackable_item · bump_item_quantity · dedupe_stackables · get_world_nodes_full · ensure_world_node · update_world_node_state · record_world_event · get_recent_world_events · set_memory_summary.

## 10. DISCREPANCY LEDGER
- B-1/A-1 art.js endpoints — RESOLVED.
- B-2 memory/lore/nudge columns dormant (code uses metadata JSONB) — OPEN (D-1).
- B-4 notes/visibility routes have no UI caller — OPEN.
- B-5 no per-user rate limit; CORS open — OPEN.
- B-6 0008_story_indexes.sql absent from repo — OPEN.
- D-5 backend stat clamp 0..999 vs frontend clampStat to Max* — ACCEPTED (AI prompt states caps; frontend enforces display).

## 11. MAINTENANCE RULES
New route → §5 row + FRONTEND §6. New db method → §8/§9 + DATABASE §4. New tag → §7 + resolver/applier + assembler + FRONTEND §5. New column → DATABASE §3 + numbered migration.

## ADDENDUM — SOCIAL & DELETE SPRINT (2026-08-17)
New model: StoryCommentRequest{content}. App version 7.6.0.
New routes (all require_user):
| Route | Guard | db_ext call | Caller |
|---|---|---|---|
| GET /api/stories/social (BEFORE /stories/{id}) | U | get_all_story_social_counts | StoryLibrary |
| GET /api/stories/{id}/social | U + check_story_access | get_story_social(story_id, user_id) → {liked, like_count, comments} | StoryDetails |
| POST /api/stories/{id}/like | U + check_story_access | toggle_story_like (toggle insert/delete; one like per user/story) | StoryDetails |
| POST /api/stories/{id}/comments | U + check_story_access | add_story_comment (content 1–500; stores username snapshot) | StoryDetails |
| DELETE /api/stories/{id}/comments/{cid} | U | delete_story_comment (comment author OR story author incl. legacy-claim) | StoryDetails |
| DELETE /api/stories/{id} | U + can_manage_story | delete_story_full (FK CASCADE wipes characters/messages/notes/playthroughs/likes/comments) | StoryDetails |
Guards unchanged otherwise. SSE pipeline unchanged.
