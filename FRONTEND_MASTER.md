# FRONTEND MASTER CONTRACT — InkMind
> Verified against commit f32ebcc + the FE-BUG-1 / A-3-B1 fix sprint.
> GOVERNANCE: APPEND-ONLY. Never remove entries or restructure until the user
> explicitly orders a refactor. Every frontend change MUST update this file and,
> if it crosses layers, BACKEND_MASTER.md / DATABASE_MASTER.md in the same commit.

## 1. STACK & BUILD
React 19.2.8 · Vite 8.1.5 · Tailwind 3.4.17 · lucide-react · react-markdown 10.1.0 · remark-gfm · idb 8.0.1. Entry index.html → src/main.jsx (StrictMode) → src/App.jsx. BASE_URL (utils/auth.js): VITE_API_URL (+ "/api") or same-origin "/api". Dev proxy: /api → localhost:8000. Theme: dark, 44px tap targets, touch-manipulation, 100dvh.

## 2. VIEW STATE MACHINE (App.jsx)
landing → LandingPage · auth → AuthPage · library → StoryLibrary · details → StoryDetails · storySetup → StoryCreator(create) · storyEdit → StoryCreator(edit, character locked) · default → chat layout (Sidebar + header + HUD + ChatWindow + ChatInput).

## 3. STAT SYSTEM (FE-BUG-1 FIXED, level-ready)
- clampStat(stat, value, stats) in App.jsx is the ONLY place HUD-side stat bounds live:
  Health 0..stats.MaxHealth (baseline 100) · Mana 0..stats.MaxMana (baseline 50) · MaxHealth/MaxMana 1..999 · other stats 0..999.
- SSE state_update STAT_UPDATE handling: if up.is_delta → current + value, else absolute; THEN clampStat. Never assign raw values.
- LEVEL SYSTEM HOOK: raising a character's MaxHealth/MaxMana (via [STAT_UPDATE: Hero.MaxHealth +20]) automatically raises the clamp — no other change needed when levels ship.
- HUD.jsx renders hp = stats.Health ?? 100 over maxHp = stats.MaxHealth ?? 100 (same for Mana/50) — follows the same keys.

## 4. PAGES & PANELS (elements → backend)
- LandingPage: Quick Chat card → requireAuth("chat"); Story Forge card ("Under Development" badge, cosmetic) → requireAuth("story"); user chip/Sign out.
- AuthPage: POST /api/auth/login|signup (15s timeout, one auto-retry on abort/Failed-to-fetch, signup 409-after-retry → auto login); remember_me chooses localStorage vs sessionStorage.
- StoryLibrary: tabs All/Mine/History. Loads GET /api/stories?scope=all|mine + GET /api/playthroughs + GET /api/stories/art (returns {id:{cover,banner}}, flattened to covers). Card shows cover, genre, title, premise, "by {author}", Art upload button (owner only → canvas 640px JPEG → POST /api/stories/{id}/art {image}). Card click → onOpenStory(full payload incl. creator_id/creator_name/played_count/is_public) → details view.
- StoryDetails: fetches GET /api/stories/{id} when premise missing (response now includes characters[].image). Shows banner (banner_image || cover_image), genre, Public/Private, title, author, premise, cast cards (image rendered when present), Continue/Begin Journey → onStartJourney, author-only Edit → storyEdit.
- StoryCreator: step 1 title/genre/premise; step 2 character (locked in edit). Create → POST /api/stories; edit save → PATCH /api/stories/{id} {title,genre,premise}.
- Chat layout: Home leaves saga; Flag = end journey (POST /api/playthroughs/{pt}/complete); settings panel; error/notice banners; completed banner → Start New Journey.
- ChatWindow: narrative vs normal bubbles; scroll "auto" while streaming else "smooth".
- ChatInput: model chip → SettingsPanel; Reasoning toggle (enable_thinking); Enter=send; Stop aborts stream.
- SettingsPanel: model picker (models.js: glm-4.7-flash "InkMind Nova", glm-4.5-flash "InkMind Pulse"), maxTokens 1024–8192, temperature 0–1.
- HUD panels: InventoryPanel (fetchInventory cache-first; Equip/Unequip/Use/Drop optimistic + HUD_ACTION), StoryMap (fetchMap; journey line + detail), CharacterSheet (stats + gear bonuses + abilities), WorldCodex (GET world-nodes + world-events; groups powers/places/people; chronicle).

## 5. UTILS CONTRACTS
- api.js: runStream (SSE; 429 retry once honoring Retry-After clamp 1–10s; silent EOF → synthetic done); streamChat/streamStory; fetchInventory/fetchMap (IndexedDB cache instant + SYNC_HUD queue); equip/unequip/use/drop optimistic; completePlaythrough; compressMemory.
- auth.js: BASE_URL, token storage, authHeaders, parseJsonSafe, friendlyHttp, describeNetworkError, withTelemetry, fetchMe, postAuth.
- telemetry.js: device/geo payload via ipwho.is (cached, silent-fail) — attached by withTelemetry.
- storage.js: localStorage quick-chat sessions (glm_chat_data) + settings (glm_chat_settings).
- localDb.js: IndexedDB inkmind_local v3 — stores user_session, stories, playthroughs, messages, library_feed, hud_cache, world_nodes. clearLocalDB() on logout (security).
- hudStore.js: cache-first getters, optimisticItemAction, applyStateUpdateToCache.
- syncQueue.js: FIFO + signature dedupe + offline pause. Processors: SYNC_LIBRARY, FETCH_STORY_DETAILS, FETCH_PLAYTHROUGH, FETCH_MESSAGES, COMPRESS_MEMORY, SYNC_HUD (inventory|map), HUD_ACTION, SYNC_WORLD_NODES. NEVER import api.js here.
- art.js: fetchStoriesArt → GET /api/art/stories?ids= · fetchCast → GET /api/stories/{id}/cast · fetchPrologue → GET /api/stories/{id}/messages?limit=3&base_only=true · uploadStoryArt → POST /api/stories/{id}/art {kind,data_url} · uploadCharacterArt → POST /api/stories/{id}/characters/{cid}/art {data_url} · fileToDataUrl (canvas 640px, 8MB cap). ALL ENDPOINTS NOW EXIST (A-3/B-1 resolved).

## 6. UI → BACKEND CALL INDEX
Boot: GET /api/health, GET /api/auth/me · Auth: POST /api/auth/{login,signup,logout} · Library: GET /api/stories?scope=, GET /api/playthroughs, GET /api/stories/art, GET /api/art/stories · Details: GET /api/stories/{id}, GET /api/stories/{id}/cast · Create/Edit: POST /api/stories, PATCH /api/stories/{id} · Art: POST /api/stories/{id}/art, POST /api/stories/{id}/characters/{cid}/art · Journey: POST /api/stories/{id}/play, GET /api/playthroughs/{pt}/messages, turn POST /api/stories/{id}/continue (SSE) · HUD: GET inventory|map|world-nodes|world-events, POST equip|unequip|use|drop|complete|compress · Quick chat: POST /api/chat/stream.

## 7. DISCREPANCY LEDGER (append-only; mark RESOLVED, never delete)
- FE-BUG-1 — HUD showed -10/100 on damage. RESOLVED 2026-08-13: delta application + clampStat in App.jsx; backend clamp in state_applier._stat_cap.
- FE-BUG-2 — SYNC_HUD has no key:'world' branch but App.jsx enqueues it (2 places); world cache refresh currently no-ops (WorldCodex fetches fresh on open, so user-visible impact is nil). OPEN.
- A-3/B-1 — utils/art.js targeted 4 nonexistent endpoints. RESOLVED 2026-08-13: endpoints implemented in main.py (see BACKEND_MASTER §5).
- FE-NOTE-1 — LandingPage "Under Development" badge on Story Forge is stale/cosmetic. OPEN (user decision).
- FE-NOTE-2 — No UI yet to upload NPC portraits (endpoint exists; art.js helper exists). OPEN (next UI task when requested).
