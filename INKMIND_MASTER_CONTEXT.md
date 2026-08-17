# INKMIND — MASTER CONTEXT & PROJECT HISTORY
> Living document. Every commit that changes code MUST append an entry to section 9 (Rule 12).
> Any AI reading this file can continue the project without prior conversation.

## 0. QUICK START FOR A NEW AI
1. You are the lead full-stack engineer of InkMind, an AI narrative-RPG platform.
2. Source of truth = the GitHub repo. Fetch any file before editing; NEVER assume contents.
   Repo: https://github.com/tricks-ter/AI-Story-Teller-Prod (branch main)
   Raw pattern: https://raw.githubusercontent.com/tricks-ter/AI-Story-Teller-Prod/main/<path>
   Live site: https://inkmind.tech
3. Read sections 2, 5, 6 BEFORE writing code.
4. Current status: Phase 5 complete (see section 9). Next work: Phase 6 (section 11).

## 1. VISION & BUSINESS IDEA
InkMind turns AI storytelling into a game: users forge story templates (genre + premise +
protagonist), then play them as private per-user sagas where an LLM narrates in 2nd person,
respects player agency, and mutates a real relational world-state (time, stats, locations,
items, abilities, backpacks) visualized in a mobile game HUD.

Business model (planned; schema already prepared):
- Freemium energy economy: stories.energy_cost, stories.is_premium and
  users.metadata.energy_credits exist (dormant); gate /play on credits in Phase 10.
- Creator marketplace: authors publish public sagas; premium sagas + revenue share.
- Subscription tier "InkMind+": ad-free, higher limits, exclusive models.
- Saga-to-EPUB export: sell "your novel, written by your choices" from completed playthroughs.
- Community layer: ratings, remix-with-credit, featured shelves, creator profiles.
- B2B: licensed interactive-fiction API for studios/education.
Target: mobile-first AI-native readers & writers; emerging markets (light model costs).

## 2. STACK & DEPLOYMENT
- Backend: FastAPI (Vercel serverless) in api/main.py; router prefix /api.
- DB: Postgres via psycopg2 — single reused conn + RLock + retry-once (_with_conn).
- AI: Z.AI SDK (zai.ZaiClient); glm-4.7-flash = "InkMind Nova" (default), glm-4.5-flash = "Pulse".
- Frontend: React 19 + Vite + Tailwind + lucide-react + react-markdown.
- Routing: root vercel.json: /api/(.*) -> api/main.py ; /(.*) -> frontend/dist/index.html.
- Migrations: DEPLOY-TIME ONLY. migrations/*.sql applied by api/migrate.py via
  .github/workflows/migrate.yml (GitHub secret DATABASE_URL; push main + dispatch).
  Runtime init_tables() = connection check ONLY. Never add runtime migrations.
- Alt hosts: render.yaml, start.sh. CI tests: .github/workflows/tests.yml (pytest api/tests -q)....
## 3. REPOSITORY MAP
    migrations/0001_core_schema.sql   users, auth_tokens, chat_*, stories, story_characters, story_messages, story_notes
    migrations/0002_playthroughs.sql  playthroughs, playthrough_characters; story_messages.playthrough_id (default 'legacy')
    migrations/0003_hardening.sql     NOT NULL + defaults everywhere
    migrations/0004_locations.sql     locations (per-playthrough discovered places)
    migrations/0005_robustness.sql    hot-path indexes, CHECKs, updated_at triggers, uniq location name
    migrations/0006_items.sql         playthrough_items / playthrough_equipment / playthrough_backpacks
    migrations/0007_visibility.sql    stories.is_public
    migrations/0008_story_indexes.sql creator/updated indexes
    migrations/0009_map.sql           locations.visit_count / last_visited_at
    api/main.py                       ALL routes; SSE generators; ownership checks; idempotency guards
    api/database.py                   Database class (~50 methods): auth, chat, stories, playthroughs,
                                      state, locations, items/equipment/backpacks/abilities, notes, tokens
    api/migrate.py                    deploy-time migration runner (schema_migrations ledger)
    api/core/auth.py                  PBKDF2; make_token (30d remember / 12h session); get_user_by_token
    api/core/prompt_assembler.py      sandwich prompt: engine rules + PLAYER AGENCY + STYLE + tag contract
                                      + live WORLD STATE (stats/abilities/carried/equipped/backpack/map) + notes
    api/core/state_resolver.py        regex-extract state tags to typed dicts; strip tags from prose
    api/core/state_applier.py         apply updates playthrough-scoped, returns applied+rejected
    api/core/resilience.py            429/5xx classify, Retry-After, jittered backoff, circuit breaker
    api/tests/                        pytest safety net (resolver, resilience, main helpers)
    frontend/src/App.jsx              view gateway + global state + SSE event router + banners
    frontend/src/components/          LandingPage, AuthPage, StoryLibrary(+details/notes/visibility),
                                      StoryCreator, ChatWindow, MessageBubble, NarrativeBubble,
                                      EmptyState, TypingIndicator, Sidebar, ChatInput, SettingsPanel,
                                      HUD, InventoryPanel, StoryMap, CharacterSheet
    frontend/src/utils/               api.js (SSE transport + 429 auto-retry + inventory/map clients),
                                      auth.js (tokens, friendly errors, withTelemetry),
                                      storage.js (localStorage quick-chat), models.js (model catalog)
    INKMIND_MASTER_CONTEXT.md         this file

## 4. DATABASE SCHEMA & RELATIONS
    users 1-N auth_tokens            users 1-N playthroughs
    users 1-N chat_sessions 1-N chat_messages
    stories 1-N story_characters | story_messages | story_notes | playthroughs
    playthroughs 1-N playthrough_characters | locations | story_messages(via playthrough_id)
    playthrough_characters 1-N playthrough_items | playthrough_equipment ; 1-1 playthrough_backpacks
    playthrough_items 1-N playthrough_equipment  (UNIQUE(character_id, slot))
Key design decisions:
- IDs are VARCHAR(36) (not UUID type) everywhere.
- JSONB for dynamic AI stats/abilities/inventory/bonuses (AI invents stat names, so JSONB not EAV).
- story_messages.playthrough_id='legacy' = author template/intro rows (security boundary; base_only reads).
- Backpack capacity = 5 + level*5; equipped items weigh nothing.
- Playthrough statuses: active / completed (constraint also allows abandoned/paused).

## 5. IMMUTABLE CODE RULES (violations = broken trust)
1. Additive-only. NEVER remove or break existing functions/features. Prefer appending new
   methods/sections. If a full-file rewrite is unavoidable, preserve EVERY prior function verbatim.
2. Every delivery starts with a CHANGELOG and ends with commit+push commands.
3. Full files only — one code block per file (Termux heredoc), never partial diffs.
4. Human-readable errors always; timeouts + one auto-retry (layered: backend backoff +
   transport retry + synthetic done on silent EOF).
5. Every INSERT fills every column; no NULLs; defaults on all columns.
6. Mobile-first UI: 44px tap targets, touch-manipulation, 100dvh.
7. React 19 auto-JSX: never use React.Fragment without importing React (blank-screen crash history).
8. Keep a ledger; verify nothing lost. If a file is unchanged, do not re-send it.
9. Schema changes = new numbered migration with IF NOT EXISTS; code must survive deploy
   ordering (try/fallback SQL patterns where a new column is referenced).
10. Per-user isolation on every endpoint: require_user, require_own_playthrough,
    check_story_access (private sagas), require_story_owner (notes/visibility).
11. Idempotent retries: 90s dedupe guards so auto-retries never duplicate user messages.
12. Update this file (section 9) on every commit that changes code.

## 6. DELIVERY FORMAT (Termux)
    cat << 'EOF' > path/to/file
    ...full file content...
    EOF
    git add .
    git commit -m "feat|fix|docs: <phase> - <summary>"
    git push

## 7. PROTOCOLS
SSE events: thinking, content, state_update(clean_content, updates, rejected, day, time_of_day,
status), error(code, retry_after, message), done, plus client-side status.
State tags (AI to world):
    [TIME_UPDATE: Day X, TimeOfDay]
    [STAT_UPDATE: Char.Stat = N]  /  [STAT_UPDATE: Char.Stat -N]
    [LOCATION_UPDATE: Name | desc=chronicle]
    [ITEM_UPDATE: Char + Item | type=, slot=, rarity=, level=, weight=, bonus.X=, desc=]
    [ITEM_UPDATE: Char - Item]
    [ABILITY_UPDATE: Char + Ability | desc=]     (powers NEVER go in backpack)
    [BAG_UPDATE: Char level N]
    [SAGA_END]
Item types: weapon/armor/accessory/consumable/material/quest (quest = undroppable).
Slots: main_hand/off_hand/head/body/ring/amulet/trinket. Rarities: common..legendary.

## 8. FEATURE INVENTORY (live)
Auth+remember-me+logout; quick chat w/ thinking; story forge; library (All/Mine/History) +
details page (premise, protagonist bio, Director's Notes author UI, Public/Private);
per-user playthroughs + history; agency-respecting SSE narration; HUD (HP/MP bars, stat chips,
location); interactive Story Map (journey line, tap-to-inspect, visit counts, current pulse);
Character Sheet (base+gear bonuses, abilities, equipped); backpack economy (weight/stack/
capacity/upgrades); equip/unequip with swap math; use consumables / drop items; abilities
ledger; item & location descriptions; rejection toasts; saga completion (flag button or
[SAGA_END]) + restart; industrial 429 resilience; cross-user isolation; pytest CI.

## 9. CHANGE HISTORY LOG  (append one bullet per code-changing commit)
- 2026-07-29 Monorepo restructure for native Vercel (vercel.json rewrites).
- Phase 1 Auth, remember-me, telemetry, read APIs, library.
- Phase 2 Engine + player agency + narrative styling + playthroughs + history; deploy-time migrations.
- Phase 3 HUD (HP/Mana/chips), locations table (0004); 0005 robustness.
- Fix New-story intro placeholder bug; Story Details view with Start/Resume Journey.
- Security hotfix Cross-user conversation leak: base_only reads + playthrough intro seeding + idempotency guards.
- Phase 4 Items/equipment/backpacks (0006), inventory panel; abilities + descriptions + location auto-detect.
- Resilience Backend jittered backoff + circuit breaker; frontend transport 429 retry; EOF hang guard.
- Pre-Phase-5 Director's Notes API+UI, is_public (0007/0008) + enforced access, logout/token purge, pytest CI.
- Phase 5 (0009) Interactive Story Map, Character Sheet, Use/Drop, saga completion + restart.
- Docs INKMIND_MASTER_CONTEXT.md created (this file).

## 10. KNOWN GAPS / BUG LEDGER (fixed vs open)
Fixed: cross-user leak; intro placeholder; stale HUD count (mirror dual-write); ability-desc no-op;
EOF hang; half-set storyContext on /play failure; unused check_story_access; notes unreachable.
Open: no per-user rate limit on own API; quick-chat is localStorage-only (DB write-only);
15-message AI memory ceiling (no rolling summary); no password reset; consumables have no
narrated effect; N+1 queries in prompt assembly (perf note); no library search/filters.

## 11. FUTURE PHASES ROADMAP
- Phase 6 Author Studio & Memory: rolling story summaries injected into prompt for 100-turn
  sagas; lorebook auto-extraction; story edit/delete; starter-location field; library
  search/filters; consumable effects via AI nudge.
- Phase 7 Intelligence: context compression, per-story model pick, adaptive difficulty.
- Phase 8 Trust & Polish: per-user token-bucket rate limit, password reset, error boundaries,
  a11y, PWA, i18n, expanded tests.
- Phase 9 Community: ratings, remix-with-credit, featured shelf, creator profiles, share links.
- Phase 10 Economy & Ops: energy-credit gate on /play, premium sagas, revenue share,
  saga-to-EPUB export, referrals, admin/metrics dashboard.

## 12. HOW AN AI SHOULD CONTINUE
1. Fetch latest files first (repo is source of truth).
2. Follow sections 5 and 6 exactly.
3. Implement the next roadmap phase or the user's request additively.
4. Append a section-9 entry.
5. Verify with user-facing checklists (Actions tab green, in-app behaviors).
- Phase 6 UI (additive): OOC-style library feed (featured banner, chips, Recently Played, Top Ranked, search) + Story Information page (cover/tags/stats/descriptions/cast/prologue preview, sticky Continue/New Session) + owner art uploads (story cover + NPC portraits) stored in DB via migration 0011_story_art.sql; new endpoints /art/stories, /stories/{id}/art, /stories/{id}/characters/{cid}/art, /stories/{id}/cast with pre-migration fallbacks; all prior functions preserved.
- Phase 6 Fix Resolved React Hook violation in StoryLibrary (moved infoTab to top level) that caused blank page on story click. Added Story Edit mode (PATCH /stories/{id}) and integrated StoryCreator with edit state.
- Phase 6 Local-First Implemented IndexedDB (idb) mirror of Postgres tables for Hot Data hydration (User, Library, Messages). Added FIFO Background Sync Queue using requestIdleCallback to fetch Warm Data without UI jank.
- Phase 6 Config Added "idb" (IndexedDB wrapper) to frontend/package.json dependencies to support local-first architecture and FIFO sync queue.
- Phase 6 Full Audit Fixed fatal ReferenceError in StoryLibrary.jsx (settersi), moved PATCH route before include_router, added missing update_story_metadata, created 0010_location_upsert_index.sql to fix Postgres ON CONFLICT crashes, added clearLocalDB() for logout security, eliminated N+1 query latency in PromptAssembler via batched get_full_playthrough_state, and fixed mobile UI scroll jank in ChatWindow.
- Phase 6 Memory & Lore Implemented dynamic context allocation (150k chars Nova / 40k chars Pulse), rolling background memory compression via /compress endpoint and syncQueue, consumable AI nudges for stat updates, and foundational Lorebook JSONB storage.
- CRITICAL FIX Rewrote api/database.py completely to fix IndentationError caused by appending methods outside the Database class. All Phase 6 methods (update_story_metadata, get_full_playthrough_state, get_recent_messages_for_context, memory/lorebook/nudge methods) are now properly inside the class. This resolves the 500 error on message send and the inventory/map placeholder issue.
- Phase 6 Local-First HUD Implemented hud_cache IndexedDB store + hudStore.js for optimistic inventory/map mutations. fetchInventory/fetchMap now return cached data instantly and queue background cloud sync. Item actions (use/equip/drop) apply optimistically to local cache before cloud reconciliation via SYNC_HUD and HUD_ACTION queue processors. AI state_update events persist to local cache for instant hydration.

- 2026-08-10 Phase 7 Foundation: world_nodes schema (0012), backend graph methods, PromptAssembler local environment injection, IndexedDB v3 world_nodes store, syncQueue SYNC_WORLD_NODES processor. Fixed missing Phase 6 DB methods.

- 2026-08-10 Phase 7B Living World: 0013 state columns (status/is_alive/relationship/wealth/power/allegiance) + world_events ledger; api/db_ext.py (story art, world state upserts w/ delta math, events, memory summary); main.py adds GET /stories/art (before /stories/{id}), POST /stories/{id}/art, world-nodes, world-events, compress routes; resolver/applier handle WORLD_STATE_UPDATE + WORLD_EVENT (auto-create entities); PromptAssembler injects [WORLD CODEX] + [RECENT WORLD EVENTS]; WebUI: cover art on library cards + owner upload (canvas-compressed), HUD World Codex panel.

- 2026-08-10 Hotfix: WorldCodex.jsx syntax error (missing closing brace) fixed — Vercel build now passes.

- 2026-08-11 Critical hotfix deployment: stat_resolver now treats "= -10" as delta (line 104), state_applier handles WORLD_STATE_UPDATE + WORLD_EVENT + stackable dedupe + ensure_world_node on LOCATION_UPDATE, db_ext gains banner editing + legacy claim + inventory dedupe + parent_id hierarchy, main.py gains PATCH /stories/{id} + banner field + dedupe_stackables call. Fixes: health no longer jumps to -10/100, coins stack instead of duplicate, world entities persist with hierarchy, banner editing works for all stories.

- 2026-08-11 Detail review flow: new StoryDetails.jsx (banner, author, premise, cast, Continue/New Journey, author-only Edit); App.jsx now routes library clicks to details view before chat, handleStartJourney wraps the playthrough+chat setup; StoryLibrary passes creator_id/creator_name/played_count/is_public in card payloads; database.list_stories_for_user now returns creator_id + creator_name so My Creations tab shows author reliably.

## 0.5 MASTER REFERENCE FILES (READ THESE TOO — mandatory)
Before ANY task, read these three contracts in addition to this file:
- FRONTEND_MASTER.md — every page/element and the exact backend call it makes
- BACKEND_MASTER.md — every route, its db methods, tables, and frontend caller
- DATABASE_MASTER.md — every table and the method→table matrix
RULE: these files are append-only. Never remove entries or restructure them unless the user
explicitly orders a refactor. When you add code, update the matching contract in the same commit.

- 2026-08-13 Contracts sprint (verified vs commit f32ebcc): created three append-only master contracts — FRONTEND_MASTER.md, BACKEND_MASTER.md, DATABASE_MASTER.md. Discrepancy ledgers added: FE-BUG-1 (App.jsx STAT_UPDATE still assigns raw value → HUD -10/100; backend already fixed), FE-BUG-2 (SYNC_HUD key 'world' no-op), A-3/B-1 (utils/art.js targets endpoints that don't exist), B-2/D-1 (memory columns dormant vs metadata JSONB), B-4 (notes/visibility routes have no UI caller), B-6/D-2 (0008_story_indexes.sql missing from repo). All future sessions must read the three masters before coding and update them with every change.

## 0.5 MASTER REFERENCE FILES (READ THESE TOO — mandatory)
Before ANY task, read these three contracts in addition to this file:
- FRONTEND_MASTER.md — every page/element, stat clamp system, and the exact backend call each action makes
- BACKEND_MASTER.md — every route, its guard, db methods, tables, and frontend caller
- DATABASE_MASTER.md — every table, the method→table matrix, migration ledger, and invariants
RULE: these files are append-only. Never remove entries or restructure them unless the
user explicitly orders a refactor. When you add code, update the matching contract(s) in
the same commit. Discrepancy ledgers are historical truth — mark entries RESOLVED, never delete.

- 2026-08-13 FE-BUG-1 + A-3/B-1 sprint: App.jsx applies STAT deltas additively + clampStat (Health 0..MaxHealth baseline 100, Mana 0..MaxMana baseline 50 — level-system ready); state_applier._stat_cap enforces the same caps server-side; new characters seeded with MaxHealth=100/MaxMana=50; prompt teaches caps + delta-only damage. A-3/B-1 resolved: implemented GET /api/art/stories?ids=, GET /api/stories/{id}/cast, POST /api/stories/{id}/characters/{cid}/art, extended ArtUpdateRequest to accept {kind,data_url}; GET /api/stories/{id} now merges cast portraits; db_ext gains set_character_image_by_id. Created FRONTEND_MASTER.md, BACKEND_MASTER.md, DATABASE_MASTER.md (append-only contracts) + this §0.5 pointer.

- 2026-08-13 Comprehensive Story Forge sprint: StoryCreator rewritten as 3-step forge (World: title/9 genres/premise/starter location/tone/public-private/cover/banner → Protagonist: name/role/background/portrait, editable in Edit mode → Review). Backend: POST /stories + PATCH /stories/{id} accept all new fields (starter_location/tone stored in stories.metadata; tone + starting region injected by PromptAssembler; starter location seeds locations+world_nodes on first play); new PATCH /stories/{id}/characters/{cid}; GET /stories/{id} merges cast portraits; art.js endpoints live (/art/stories, /cast, characters/{cid}/art, {kind,data_url} accepted). FE-BUG-1 RESOLVED in App.jsx (delta stats + clampStat HP 0..MaxHealth, MP 0..MaxMana, level-ready). DB unchanged (metadata JSONB carries new keys — additive, no migration needed).

- 2026-08-13 Comprehensive Story Forge sprint (re-applied — verified missing from f32ebcc): StoryCreator is now a 3-step forge (World: title/9 genres/premise/starter location/tone/public-private/cover+banner upload → Protagonist: name/role/background/portrait, editable in Edit mode → Review). Backend: POST /stories + PATCH /stories/{id} accept all new fields (starter_location/tone in stories.metadata); new GET /art/stories, GET /stories/{id}/cast, PATCH /stories/{id}/characters/{cid}, POST /stories/{id}/characters/{cid}/art; GET /stories/{id} merges cast portraits; starter location seeds locations+world_nodes+current_location on first play; new characters seed MaxHealth=100/MaxMana=50. FE-BUG-1 resolved in App.jsx (delta stats + clampStat HP 0..MaxHealth, MP 0..MaxMana). db_ext gains set_character_image_by_id / update_story_character / set_story_metadata_keys. No schema change (metadata JSONB + existing columns).

## 0.5 MASTER REFERENCE FILES (READ THESE TOO — mandatory)
Before ANY task read FRONTEND_MASTER.md, BACKEND_MASTER.md, DATABASE_MASTER.md in
addition to this file. They are append-only contracts: never remove entries or
restructure until the user explicitly orders a refactor; update them in the same
commit as any code change.

- 2026-08-13 Comprehensive forge + masters sprint: StoryDetails ALWAYS fetches full story (banner/cover/cast portraits now render; starter-location + tone chips); get_story_detail merges character images; comprehensive 3-step StoryCreator (images, visibility, starter location, tone, portrait; full edit); App.jsx edit passthrough + FE-BUG-1 clampStat fix; backend accepts full create/update payloads + art.js routes (/art/stories, /cast, characters/{cid}/art, PATCH characters); new chars seed MaxHealth/MaxMana; created FRONTEND_MASTER.md, BACKEND_MASTER.md, DATABASE_MASTER.md + this §0.5 pointer.

- 2026-08-17 Social & Delete sprint: migration 0014 (story_likes + story_comments); backend routes GET /stories/social, GET/POST /stories/{id}/social & /comments, DELETE comment, POST /stories/{id}/like toggle, DELETE /stories/{id} (author-only, cascade); StoryDetails gains like button, comments (post/delete), tap-to-expand cast backgrounds, author Delete (double-tap confirm); StoryLibrary cards show like/comment counts; master files updated via append-only addenda.

- 2026-08-17 UX Workflow sprint (base b65ef68, frontend-only): library search/genre-filter/sort + Recently Played shelf + skeleton loaders + global toast system (utils/toast.js + Toaster.jsx) + share deep-link (?story=<id> handled in App, Share button copies link) + onboarding nudge. Created FRONTEND_MASTER.md (was missing from repo); addenda to BACKEND/DATABASE masters (unchanged). No backend/DB changes; all social/like/comment/delete features from b65ef68 preserved.

- 2026-08-17 Optimistic social sprint: FE-BUG-1 fixed (App.jsx delta+clamp, level-ready); FE-BUG-2 fixed (SYNC_HUD 'world' branch); likes/comments now optimistic (instant UI + SOCIAL_ACTION background queue with rollback/toast on failure); likes idempotent server-side (LikeRequest{liked}, set_story_like ON CONFLICT DO NOTHING, migration 0015 placeholder); StoryDetails paints social from hud_cache instantly; Share copies deep link (private warning); Toaster + toast bus added; master contracts updated via addenda.
