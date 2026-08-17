# FRONTEND MASTER CONTRACT — InkMind
> Verified vs commit b65ef68 + UX Workflow sprint. APPEND-ONLY: never remove entries or
> restructure until the user explicitly orders a refactor. Update the matching entry in
> the same commit as any code change.

## 1. STACK & BUILD
React 19.2.8 · Vite 8.1.5 · Tailwind 3.4.17 · lucide-react · react-markdown+gfm · idb 8.0.1.
Entry index.html → main.jsx (StrictMode) → App.jsx. BASE_URL (utils/auth.js): VITE_API_URL (+"/api") or same-origin "/api". Dev proxy /api → localhost:8000. Dark theme, 44px targets, 100dvh.

## 2. VIEW STATE MACHINE (App.jsx)
landing → auth (requireAuth) · library → details (handleOpenStory) · storySetup → StoryCreator(create) · storyEdit → StoryCreator(edit) · default = chat layout (Sidebar+header+HUD+ChatWindow+ChatInput).
SHARE DEEP-LINK: App reads ?story=<id> on boot (after auth), fetches GET /stories/{id}, opens details, cleans the URL.

## 3. PAGES & ELEMENTS → BACKEND CALLS
- LandingPage: Quick Chat / Story Forge cards; Sign In/Out.
- AuthPage: POST /auth/login|signup (15s timeout, one retry, 409→auto-login).
- StoryLibrary: tabs All/Mine/History. Loads GET /stories?scope=all|mine + /playthroughs + /stories/art + /stories/social (5 parallel). UX: search (title/premise), genre chips, sort (recent/played/az), skeleton loaders, Recently Played shelf (All tab), onboarding nudge (localStorage inkmind_onboarded), owner Art upload → POST /stories/{id}/art {image} + toast. Card payload: id/title/genre/premise/character_*/creator_id/creator_name/is_public/played_count/current_day/time_of_day/playthrough_id. Cards show cover, ♥ likes, 💬 comments.
- StoryDetails: fetch GET /stories/{id} + /stories/{id}/social. Renders banner (banner_image||cover_image), genre/public/starter_location chips, tone, premise, cast (tap-to-expand backgrounds, portraits), Like toggle (POST /like), Comments (POST/DELETE /comments), author-only Edit + Delete (DELETE /stories/{id}, double-tap), Share (copies ?story=<id> link) + toasts. Continue/Begin Journey → onStartJourney.
- StoryCreator: 3 steps (World: title/genre/premise/starterLocation/tone/visibility/cover/banner · Protagonist: name/role/background/portrait · Review). Create → POST /stories; Edit → PATCH /stories/{id}. Character locked in edit mode.
- Chat layout: header (Home/end-journey flag/Settings), error/notice banners, completed banner, HUD, ChatWindow, ChatInput.
- HUD: HP/MP bars (Health/MaxHealth, Mana/MaxMana defaults 100/50), stat chips, location → StoryMap; buttons WorldCodex/CharacterSheet/StoryMap/InventoryPanel.
- InventoryPanel: fetchInventory (cache-first); Abilities/Equipped/Carried (×qty, Equip/Use/Drop) optimistic + HUD_ACTION.
- StoryMap: fetchMap; journey line + detail.
- CharacterSheet: stats + gear bonuses, abilities, equipped.
- WorldCodex: GET world-nodes + world-events; groups powers/places/people; chronicle.

## 4. UTILS
api.js: runStream (SSE; one 429 retry w/ Retry-After; synthetic done on silent EOF), streamChat/streamStory, fetchInventory/fetchMap (IndexedDB-first + SYNC_HUD), optimistic equip/unequip/use/drop, completePlaythrough, compressMemory.
auth.js: BASE_URL, token storage, authHeaders, parseJsonSafe, friendlyHttp, describeNetworkError, withTelemetry, fetchMe, postAuth.
toast.js + Toaster.jsx: global toast bus (success/error/info, 3.5s auto-dismiss). Toaster mounted in StoryLibrary & StoryDetails.
telemetry.js: device/geo payload (ipwho.is, silent-fail).
storage.js: localStorage quick-chat (glm_chat_data) + settings (glm_chat_settings).
models.js: glm-4.7-flash="InkMind Nova", glm-4.5-flash="InkMind Pulse" (ids never shown).
localDb.js: IndexedDB inkmind_local v3 — user_session, stories, playthroughs, messages(idx), library_feed, hud_cache(idx playthrough_id), world_nodes(idx playthrough_id/parent_id); clearLocalDB on logout.
hudStore.js: cache getters/setters, optimisticItemAction, applyStateUpdateToCache.
syncQueue.js: FIFO + signature dedupe + offline pause. Processors SYNC_LIBRARY/FETCH_STORY_DETAILS/FETCH_PLAYTHROUGH/FETCH_MESSAGES/COMPRESS_MEMORY/SYNC_HUD(inventory|map)/HUD_ACTION/SYNC_WORLD_NODES. NEVER imports api.js.
art.js: fetchStoriesArt/fetchCast/fetchPrologue/uploadStoryArt/uploadCharacterArt/fileToDataUrl.

## 5. SSE state_update HANDLING (App.jsx)
clean_content → bubble; rejected → notice; LOCATION_UPDATE → current_location; STAT_UPDATE → delta-additive + clampStat (Health 0..MaxHealth, Mana 0..MaxMana, Max* 1..999, others 0..999) — FE-BUG-1 RESOLVED; ITEM/ABILITY_UPDATE → metadata mirrors; then applyStateUpdateToCache + SYNC_HUD(inventory, world); done → COMPRESS_MEMORY.

## 6. UI → BACKEND INDEX
Boot GET /health + /auth/me · auth POST /auth/* · library GET /stories, /playthroughs, /stories/art, /stories/social · deep-link & details GET /stories/{id} · social GET /stories/{id}/social, POST /stories/{id}/like, POST|DELETE /stories/{id}/comments · create POST /stories · edit PATCH /stories/{id} · delete DELETE /stories/{id} · art POST /stories/{id}/art · journey POST /stories/{id}/play · turn POST /stories/{id}/continue · HUD GET inventory|map|world-nodes|world-events · actions POST equip|unequip|use|drop|complete|compress · chat POST /chat/stream.

## 7. DISCREPANCY LEDGER (append-only; mark RESOLVED, never delete)
- FE-BUG-1 HUD -10/100 on damage — RESOLVED (clampStat + delta-additive).
- FE-BUG-2 SYNC_HUD key 'world' enqueued but processor has no 'world' branch (no-op; WorldCodex fetches fresh on open) — OPEN.
- A-3/B-1 art.js endpoints — RESOLVED (all routes exist).
- DOC-1 README.md still describes legacy GLM Chat /sessions — OPEN.
- A-4 LandingPage "Under Development" badge on Story Forge is stale — OPEN (cosmetic).
- UX-1 Search/filter/sort, Recently Played, skeletons, toasts, share deep-link, onboarding — RESOLVED (this sprint, frontend-only).

## 8. MAINTENANCE RULES
New component → §3 entry + §6 for its calls. New util → §4. New IndexedDB store → bump DB_VERSION + §4. Any backend call here must exist in BACKEND_MASTER §5 first.

## ADDENDUM — OPTIMISTIC SOCIAL SPRINT (2026-08-17)
- FE-BUG-1 RESOLVED: App.jsx STAT_UPDATE adds deltas to the current value, clamps Health 0..MaxHealth (def 100) / Mana 0..MaxMana (def 50) — level-ready.
- FE-BUG-2 RESOLVED: syncQueue SYNC_HUD now handles key 'world' (world-nodes + world-events → hud_cache 'world').
- New SOCIAL_ACTION queue processor: like (idempotent explicit set {liked}), comment_add (rollback + toast on failure via 'inkmind-social-fail' window event), comment_delete (404 tolerated).
- StoryDetails v3: optimistic like/comment post/delete (instant UI, zero latency), social painted from hud_cache('social') instantly then cloud-refreshed, Share button copies /?story=<id> (private sagas warn only-author-can-open), Toaster mounted in chat layout.
- New utils/toast.js bus + components/Toaster.jsx.
- Access rule verified: any logged-in user can like/comment/share on PUBLIC sagas (require_user + check_story_access); private sagas remain author-only.
## ADDENDUM — SOCIAL QUEUE LATENCY MODEL
UI writes instantly → local cache (hud_cache 'social') → SOCIAL_ACTION reconciles with DB in background (requestIdleCallback, offline pause, dedupe). Failure paths: failed comment is rolled back locally + toast; failed like is logged (next social fetch corrects the count).
