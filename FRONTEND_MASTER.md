# FRONTEND MASTER CONTRACT — InkMind
> Verified vs commit f32ebcc + "comprehensive forge + masters" commit. APPEND-ONLY:
> never remove entries or restructure until the user explicitly orders a refactor.
> Update the matching entry in the same commit as any code change.

## 1. STACK & BUILD
React 19.2.8 · Vite 8.1.5 · Tailwind 3.4.17 · lucide-react · react-markdown+gfm · idb 8.0.1.
Entry index.html → main.jsx (StrictMode) → App.jsx. BASE_URL (utils/auth.js): VITE_API_URL (+"/api") or same-origin "/api". Dev proxy /api → localhost:8000. Dark theme, 44px targets, 100dvh.

## 2. VIEW STATE MACHINE (App.jsx)
landing → auth (requireAuth) · library → details (handleOpenStory) · storySetup → StoryCreator(create) · storyEdit → StoryCreator(edit) · default = chat layout (Sidebar+header+HUD+ChatWindow+ChatInput).

## 3. PAGES & ELEMENTS → BACKEND CALLS
- LandingPage: Quick Chat card → requireAuth("chat"); Story Forge card ("Under Development" badge, cosmetic) → requireAuth("story"); Sign In/Sign out.
- AuthPage: POST /api/auth/login|signup (15s timeout; one auto-retry on abort/Failed-to-fetch; signup 409-after-retry → auto login); remember_me → localStorage vs sessionStorage via saveAuth.
- StoryLibrary: tabs All/Mine/History. Loads GET /api/stories?scope=all|mine + GET /api/playthroughs + GET /api/stories/art (map {id:{cover,banner}} flattened). Cards: cover img, genre chip, owner-only Art upload (canvas 640px → POST /api/stories/{id}/art {image}), "by {creator_name}", Played/New/Day. Card click → onOpenStory(full payload: id, creator_id/name, is_public, played_count, ...).
- StoryDetails: ALWAYS fetches GET /api/stories/{id} (card payloads lack image columns). Renders banner (banner_image||cover_image), genre/public/private chips, starter_location chip, tone line, premise, cast cards WITH portraits (c.image), Continue/Begin Journey → POST via handleStartJourney, author-only Edit → storyEdit.
- StoryCreator: 3 steps. 1) World: title, genre (9), premise, starterLocation, tone, Public/Private toggle, cover+banner ImageFields (utils/art.js fileToDataUrl). 2) Protagonist: name/role/background/portrait; edit mode allows character edits (note: new journeys only). 3) Review + Save. Create → POST /api/stories (full payload). Edit → PATCH /api/stories/{id} (full payload via App.handleUpdateStory passthrough).
- Chat layout: header (Home, title/Day, Flag end-journey double-tap → POST /playthroughs/{pt}/complete, Settings), error/notice banners, completed banner, HUD, ChatWindow, ChatInput.
- HUD: HP bar Health/MaxHealth, MP bar Mana/MaxMana (defaults 100/50), stat chips, location chip → StoryMap; buttons: WorldCodex, CharacterSheet, StoryMap, InventoryPanel(count).
- InventoryPanel: fetchInventory (cache-first); Abilities / Equipped (Unequip) / Carried (name ×qty, Equip/Use/Drop) via optimistic api helpers + HUD_ACTION.
- StoryMap: fetchMap; journey line + detail (description, visits, discovered, last visited).
- CharacterSheet: stats (+gear bonuses), abilities, equipped.
- WorldCodex: GET world-nodes + world-events; groups powers/places/people; status tone chips; chronicle.

## 4. UTILS
api.js: runStream (SSE; 429 retry once w/ Retry-After clamp 1–10s; synthetic done on silent EOF), streamChat/streamStory, fetchInventory/fetchMap (IndexedDB-first + SYNC_HUD), equip/unequip/use/drop (optimistic + HUD_ACTION), completePlaythrough, compressMemory.
auth.js: BASE_URL, token storage, authHeaders, parseJsonSafe, friendlyHttp, describeNetworkError, withTelemetry, fetchMe, postAuth.
telemetry.js: device/geo payload (ipwho.is, silent-fail).
storage.js: localStorage quick-chat sessions (glm_chat_data) + settings (glm_chat_settings).
models.js: glm-4.7-flash="InkMind Nova", glm-4.5-flash="InkMind Pulse" (ids never shown).
localDb.js: IndexedDB inkmind_local v3 — user_session, stories, playthroughs, messages(idx session_id/playthrough_id), library_feed, hud_cache(idx playthrough_id), world_nodes(idx playthrough_id/parent_id); clearLocalDB on logout.
hudStore.js: cache getters/setters, optimisticItemAction, applyStateUpdateToCache, getCachedStoryContext.
syncQueue.js: FIFO + signature dedupe + offline pause + requestIdleCallback. Processors: SYNC_LIBRARY, FETCH_STORY_DETAILS, FETCH_PLAYTHROUGH, FETCH_MESSAGES, COMPRESS_MEMORY, SYNC_HUD(inventory|map), HUD_ACTION, SYNC_WORLD_NODES. NEVER imports api.js.
art.js: fetchStoriesArt, fetchCast, fetchPrologue, uploadStoryArt{kind,data_url}, uploadCharacterArt{data_url}, fileToDataUrl(640px, q0.82, 8MB cap).

## 5. SSE state_update HANDLING (App.jsx)
clean_content → bubble; rejected → notice; LOCATION_UPDATE → current_location; STAT_UPDATE → delta-additive + clampStat (Health 0..MaxHealth, Mana 0..MaxMana, Max* 1..999, others 0..999) — FE-BUG-1 RESOLVED; ITEM_UPDATE → inventory mirror; ABILITY_UPDATE → abilities mirror; then applyStateUpdateToCache + SYNC_HUD(inventory, world); done → COMPRESS_MEMORY.

## 6. UI → BACKEND INDEX
Boot GET /health + /auth/me · auth POST /auth/* · library GET /stories, /playthroughs, /stories/art · details GET /stories/{id} · create POST /stories · edit PATCH /stories/{id} (+ PATCH /stories/{id}/characters/{cid}, POST .../art, POST .../characters/{cid}/art available) · journey POST /stories/{id}/play · turn POST /stories/{id}/continue · HUD GET inventory|map|world-nodes|world-events · actions POST equip|unequip|use|drop|complete|compress · chat POST /chat/stream · art.js GET /art/stories, /stories/{id}/cast.

## 7. DISCREPANCY LEDGER (append-only; mark RESOLVED, never delete)
- FE-BUG-1 HUD -10/100 on damage — RESOLVED (clampStat + delta-additive).
- FE-BUG-2 SYNC_HUD key 'world' enqueued but processor has no 'world' branch (no-op; WorldCodex fetches fresh on open) — OPEN.
- A-3/B-1 art.js endpoints missing — RESOLVED (all routes exist).
- DOC-1 README.md still describes legacy GLM Chat /sessions — OPEN.
- A-4 LandingPage "Under Development" badge stale — OPEN (cosmetic).

## 8. MAINTENANCE RULES
New component → §3 entry + §6 for its calls. New util → §4. New IndexedDB store → bump DB_VERSION + §4. Any backend call here must exist in BACKEND_MASTER §5 first.
