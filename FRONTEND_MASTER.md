# FRONTEND MASTER CONTRACT — InkMind
> Verified against commit f32ebcc (branch main, 2026-08-13).
>
> GOVERNANCE (immutable): (1) APPEND-ONLY — never remove entries or restructure unless the
> user explicitly orders a refactor; update the matching entry in the same commit. (2) Keep
> BACKEND_MASTER.md and DATABASE_MASTER.md consistent with any change. (3) Items marked
> ⚠ DISCREPANCY are verified cross-layer mismatches — fix or explicitly accept them.
>
> HOW TO USE: find the file in §2, read its section in §4–§6, then check §8 (call index)
> before changing any frontend behavior.

## 1. STACK & BUILD
- React 19.2.8 · Vite 8.1.5 · Tailwind 3.4.17 · lucide-react 1.27.0 · react-markdown 10.1.0 · remark-gfm 4.0.1 · idb 8.0.1.
- Entry: index.html → src/main.jsx (StrictMode) → src/App.jsx. Title "InkMind — AI Story Teller".
- Theme: dark gray-950/900, purple/blue brand, 44px tap targets, touch-manipulation, 100dvh.
- API base (utils/auth.js): if VITE_API_URL set, use it (+ "/api" appended if missing); else same-origin "/api".
- Dev proxy: vite.config.js forwards /api → http://localhost:8000.
- Deploy: root vercel.json builds frontend and rewrites /api/(.*) → /api/main.py, /(.*) → /index.html.

## 2. FILE MAP
| File | Role |
|---|---|
| src/App.jsx | View gateway, global state, SSE event router, error/notice banners |
| src/components/LandingPage.jsx | Hub (Quick Chat / Story Forge cards) |
| src/components/AuthPage.jsx | Login / signup |
| src/components/StoryLibrary.jsx | Library tabs (All/Mine/History), cover art, owner art upload |
| src/components/StoryDetails.jsx | Story review page (Continue/New Journey, author-only Edit) |
| src/components/StoryCreator.jsx | Forge wizard + Edit mode |
| src/components/Sidebar.jsx | Quick-chat session list (localStorage) |
| src/components/ChatWindow.jsx | Message list + scroll behavior |
| src/components/ChatInput.jsx | Composer, model chip, reasoning toggle |
| src/components/MessageBubble.jsx | Quick-chat bubble (markdown, thinking block, copy) |
| src/components/NarrativeBubble.jsx | Story bubble (dialogue vs narration styling) |
| src/components/TypingIndicator.jsx / EmptyState.jsx | Stream placeholder / suggestions |
| src/components/SettingsPanel.jsx | Model / maxTokens / temperature |
| src/components/HUD.jsx | In-saga top bar (HP/MP, panel buttons) |
| src/components/InventoryPanel.jsx | Backpack (abilities/equipped/carried, actions) |
| src/components/StoryMap.jsx | Journey line + place inspector |
| src/components/CharacterSheet.jsx | Stats (+gear bonuses), abilities, equipped |
| src/components/WorldCodex.jsx | Living-world entities + event chronicle |
| src/utils/api.js | SSE transport, cache-first HUD fetchers, optimistic actions |
| src/utils/auth.js | Token storage, headers, BASE_URL, error text, withTelemetry |
| src/utils/telemetry.js | Device/geo telemetry (attached via withTelemetry) |
| src/utils/storage.js | localStorage quick-chat sessions + settings |
| src/utils/models.js | Model catalog (public names ↔ API ids) |
| src/utils/localDb.js | IndexedDB wrapper (stores v3) |
| src/utils/hudStore.js | Optimistic HUD cache mutations |
| src/utils/syncQueue.js | Background FIFO sync queue |
| src/utils/art.js | ⚠ DISCREPANCY A-3 — orphaned helpers for endpoints that do not exist |

## 3. APP SHELL — src/App.jsx
### 3.1 View state machine
| view | Renders | Entered by |
|---|---|---|
| landing | LandingPage | boot, logout, Home button |
| auth | AuthPage | requireAuth when logged out |
| library | StoryLibrary | authed "story" action, back from details |
| details | StoryDetails | library card click (handleOpenStory), after create/update |
| storySetup | StoryCreator (create) | Library "New" |
| storyEdit | StoryCreator (edit) | StoryDetails "Edit" (author only) |
| (default) | Chat layout (Sidebar+header+HUD+ChatWindow+ChatInput) | Quick Chat, or handleStartJourney |

### 3.2 Key handlers → backend
| Handler | Call(s) | Notes |
|---|---|---|
| boot effect | GET /api/health; GET /api/auth/me | me → saveLocalUser + queue SYNC_LIBRARY; bad token → clearAuth |
| handleLogout | POST /api/auth/logout | then clearAuth() + clearLocalDB() (cross-user cache safety) |
| handleOpenStory(story) | none | sets detailsStory, view=details |
| handleStartJourney(story) | POST /api/stories/{id}/play → GET /api/playthroughs/{pt}/messages?limit=100 (fallback GET /api/stories/{id}/messages?base_only=true) | builds finalContext, caches story/playthrough/messages + applyStateUpdateToCache; queues SYNC_HUD(inventory,map,world)+COMPRESS_MEMORY |
| handleStartStory(data) | POST /api/stories | then opens details view |
| handleUpdateStory(id,data) | PATCH /api/stories/{id} | sends title/genre/premise; returns to details |
| handleEndJourney | POST /api/playthroughs/{pt}/complete | double-tap confirm (Flag button) |
| sendMessage(text) | streamStory → POST /api/stories/{id}/continue (SSE) or streamChat → POST /api/chat/stream (SSE) | see §7 |

### 3.3 SSE state_update handling (story mode) — CRITICAL
On state_update: sets clean content; rejected updates → notice "🎒 {label} left behind ({reason})"; then mutates storyContext:
- LOCATION_UPDATE → current_location
- STAT_UPDATE → stats[up.stat] = up.value   ⚠ FE-BUG-1 (PENDING FIX): raw value is assigned. When the backend sends a delta (is_delta true, e.g. -10) the HUD shows -10/100. Required change: stats[up.stat] = up.is_delta ? ((stats[up.stat] ?? 100) + up.value) : up.value;
- ITEM_UPDATE → add/remove name in metadata.inventory mirror
- ABILITY_UPDATE → add/remove {name, description} in metadata.abilities
Then applyStateUpdateToCache(ptId, ctx) + queue SYNC_HUD(inventory, world). On done: queue COMPRESS_MEMORY.

## 4. PAGES
### 4.1 LandingPage
InkMind logo + tagline; user chip / Sign In / Sign out; two cards: Quick Chat (blue, MessageSquare) → requireAuth("chat"); Story Forge (purple, BookOpen, amber "Under Development" badge) → requireAuth("story"); footer "Powered by InkMind Nova & Pulse Models". Background: animated purple/blue blur orbs.
### 4.2 AuthPage
Fields: username, password, remember-me (login only). Mode toggle login↔signup. POST /api/auth/{login|signup} with 15s timeout; on AbortError/Failed-to-fetch retries once ("Server is waking up"); signup 409 after retry → auto-switch to login. Success → saveAuth(token,user,remember) → onAuthed.
### 4.3 StoryLibrary
Header: back, "Story Forge" + username, New button. Tabs: All Sagas / My Creations / History. Load: 4 parallel GETs — /api/stories?scope=all, ?scope=mine, /api/playthroughs, /api/stories/art. Art map {id:{cover,banner}} flattened to covers. Card: cover (or gradient placeholder), genre chip, Art upload button (only when creator_name === user.username; canvas-downscale 640px JPEG → POST /api/stories/{id}/art body {image}), title, premise, footer "{character_name} · by {author} · {Played|New|Day X}". Click → onOpenStory(payload) with full row (id, title, genre, premise, character_name/role, creator_id, creator_name, is_public, played_count, current_day, time_of_day, playthrough_id for history).
### 4.4 StoryDetails
Fetches GET /api/stories/{id} if premise missing. Shows: banner (banner_image || cover_image), genre chip, Public/Private badge, title, "by {author}", premise, cast cards (image or sparkle placeholder, name, "You" chip on is_player, role, background), "no cover art" hint. Buttons: Continue Journey (played_count>0) / Begin New Journey → onStartJourney; Back to Library; Edit (only if creator_id === user.id OR creator_id missing/'legacy-system') → onEdit.
### 4.5 StoryCreator
2-step wizard. Step 1: title, genre select (Fantasy/Sci-Fi/Cyberpunk/Lovecraftian Horror/Modern Slice of Life), premise. Step 2: character name/role/background — LOCKED in edit mode (preserves playthroughs). Finish → onStart(data) (POST /api/stories) or onUpdate(initialData.id, data) (PATCH).
### 4.6 Chat layout (default view)
Header: Sidebar toggle (mobile), Home (leaves saga), title + "Day N · TimeOfDay · character", Flag=end journey (double-tap), Settings, online dot. Banners: error (red, dismiss), notice (amber, dismiss), saga-completed (purple + "Start New Journey").
### 4.7 ChatWindow / bubbles
Empty story state: italic prompt + suggestions ["Look around carefully","Move forward"]. Empty chat state: EmptyState 4 suggestion cards. Scroll behavior: "auto" while streaming else "smooth" (mobile jank fix). msg.narrative ? NarrativeBubble : MessageBubble. NarrativeBubble splits "quoted" dialogue (white) vs narration (italic gray). MessageBubble: markdown(gfm), collapsible ThinkingBlock, copy button, streaming cursor.
### 4.8 ChatInput
Model chip (opens SettingsPanel, shows public model name), Reasoning ON/OFF toggle (Brain), auto-grow textarea (max 180px), Enter=send / Shift+Enter=newline, Send (brand) / Stop (red) button. Disabled while streaming or saga completed.
### 4.9 Sidebar / SettingsPanel
Sidebar: "InkMind Chat", New Chat, session list (title, msg count, relative time, hover delete) from localStorage. SettingsPanel: model picker (MODELS list), Max Tokens slider 1024–8192 step 256, Temperature 0–1 step 0.1.

## 5. HUD PANELS
| Panel | Opens via | Data source | Content |
|---|---|---|---|
| HUD bar | always in saga | storyContext | HP bar (Health/MaxHealth), MP bar (Mana/MaxMana), 2 stat chips, location chip |
| InventoryPanel | Backpack button | api.fetchInventory | Load bar used/capacity, gear bonuses; Abilities; Equipped (Unequip); Carried rows show name + ×quantity when >1, type/lv/weight/rarity, desc; buttons Equip/Use(consumable)/Drop(not quest) |
| StoryMap | location chip or Map icon | api.fetchMap | Journey line (current=pulsing purple), place detail: description, visits, discovered, last visited |
| CharacterSheet | UserRound | fetchInventory + storyContext | Stats (+green gear bonus), abilities, equipped |
| WorldCodex | ScrollText | GET world-nodes + world-events | Groups: Kingdoms & Houses (region/faction/economy_state), Settlements & Places, People (NPC relationship ±N, skull if dead); status chips (red=war/hostile, green=prosper/rising, amber=tense); Chronicle of Events (Day N — type: desc) |

## 6. UTILS CONTRACTS
- api.js: runStream POSTs withTelemetry body, parses data: SSE lines; 429 → retry once honoring Retry-After (clamp 1–10s) with status event; non-ok → error; silent EOF (no done/error) → synthetic done. streamChat/streamStory return abort fn. fetchInventory/fetchMap return IndexedDB cache instantly + queue SYNC_HUD; cold cache → API fetch + cache. equipItem/unequipItem/useItem/dropItem do optimistic cache mutation + queue HUD_ACTION, return {ok:true, optimistic:true}. completePlaythrough/compressMemory POST helpers.
- auth.js: BASE_URL; getToken/getSavedUser (local or session storage); saveAuth/clearAuth; authHeaders (Bearer); parseJsonSafe; friendlyHttp; describeNetworkError; withTelemetry(body); fetchMe; postAuth.
- telemetry.js: getTelemetry (cached) — UA/browser/OS/device, screen/viewport/cores/memory/touch, timezone/language, geo via ipwho.is (5s timeout). Attached to signup/login/story create/continue/play/update bodies.
- storage.js: quick-chat sessions under localStorage key glm_chat_data; settings under glm_chat_settings {model, maxTokens:4096, temperature:0.7, enableThinking:true}.
- models.js: glm-4.7-flash="InkMind Nova" (Recommended), glm-4.5-flash="InkMind Pulse". API ids never shown in UI. DEFAULT_MODEL_ID=glm-4.7-flash.
- localDb.js: IndexedDB inkmind_local v3 — see §9.
- hudStore.js: getCached/cacheInventory/Map; optimisticItemAction(pid, use|drop|equip|unequip, itemId); applyStateUpdateToCache(pid, storyContext) (hud_cache key story_context); getCachedStoryContext.
- syncQueue.js: FIFO, signature-dedupe, pauses offline (navigator.onLine), resumes on online, runs via requestIdleCallback. Processors: SYNC_LIBRARY, FETCH_STORY_DETAILS, FETCH_PLAYTHROUGH, FETCH_MESSAGES, COMPRESS_MEMORY, SYNC_HUD, HUD_ACTION, SYNC_WORLD_NODES. NEVER import api.js here (circular). ⚠ FE-BUG-2: SYNC_HUD handles key 'inventory' and 'map' only — no 'world' branch — but App.jsx enqueues key:'world' in 2 places, so that task is a silent no-op.
- art.js: ⚠ A-3 — fetchStoriesArt (GET /api/art/stories?ids=), fetchCast (GET /api/stories/{id}/cast), uploadStoryArt body {kind,data_url}, uploadCharacterArt (POST /api/stories/{id}/characters/{cid}/art) target endpoints that DO NOT exist in main.py (backend expects POST /api/stories/{id}/art body {image,banner}). Only fetchPrologue (GET /api/stories/{id}/messages?limit=3&base_only=true) works. Currently unused by any component.

## 7. SSE EVENT CONTRACT (client side)
thinking{content} → append to streaming thinking; content{content} → append; status{message} → statusText; state_update{clean_content,updates,rejected,day,time_of_day,status} → §3.3; error{code,retry_after,message} → error banner; done → finalize message.

## 8. UI → BACKEND CALL INDEX
| UI action | Method + Path | Caller |
|---|---|---|
| App boot | GET /api/health, GET /api/auth/me | App effect |
| Login/Signup | POST /api/auth/login, /api/auth/signup | AuthPage |
| Logout | POST /api/auth/logout | App |
| Library load | GET /api/stories?scope=all|mine, GET /api/playthroughs, GET /api/stories/art | StoryLibrary.load |
| Cover upload | POST /api/stories/{id}/art {image} | StoryLibrary.uploadArt |
| Open details | GET /api/stories/{id} | StoryDetails effect |
| Start/create journey | POST /api/stories/{id}/play | App.handleStartJourney |
| Seed messages | GET /api/playthroughs/{pt}/messages, GET /api/stories/{id}/messages?base_only=true | App.handleStartJourney |
| Story turn | POST /api/stories/{id}/continue (SSE) | api.streamStory |
| Quick chat turn | POST /api/chat/stream (SSE) | api.streamChat |
| Create saga | POST /api/stories | App.handleStartStory |
| Edit saga | PATCH /api/stories/{id} | App.handleUpdateStory |
| End journey | POST /api/playthroughs/{pt}/complete | App.handleEndJourney |
| Inventory open | GET /api/playthroughs/{pt}/inventory | api.fetchInventory (cache-first) |
| Map open | GET /api/playthroughs/{pt}/map | api.fetchMap (cache-first) |
| Item actions | POST /api/playthroughs/{pt}/{equip,unequip,use,drop} | syncQueue HUD_ACTION |
| Codex open | GET /api/playthroughs/{pt}/world-nodes, /world-events | WorldCodex |
| Background | SYNC_LIBRARY/FETCH_*/COMPRESS_MEMORY/SYNC_HUD/HUD_ACTION/SYNC_WORLD_NODES | syncQueue |

## 9. INDEXEDDB SCHEMA (inkmind_local, v3)
| Store | keyPath | Indexes | Written by |
|---|---|---|---|
| user_session | id | — | saveLocalUser |
| stories | id | — | saveLocalStory |
| playthroughs | id | — | saveLocalPlaythrough |
| messages | id | session_id, playthrough_id | saveLocalMessages |
| library_feed | user_id | — | SYNC_LIBRARY |
| hud_cache | cache_key ({ptId}:{key}) | playthrough_id | hudStore / SYNC_HUD |
| world_nodes | id | playthrough_id, parent_id | SYNC_WORLD_NODES |
clearLocalDB() wipes all stores on logout.

## 10. KNOWN DISCREPANCIES & PENDING FIXES (resolve; don't delete until fixed)
- FE-BUG-1 (critical, user-reported): App.jsx state_update STAT_UPDATE assigns raw delta to stats → HUD shows -10/100. Fix in §3.3. Backend resolver/applier already correct.
- FE-BUG-2: SYNC_HUD has no key:'world' branch but App.jsx enqueues it (2 places) → world cache never refreshes via queue. Add a world branch (fetch world-nodes+events → setHudCache 'world') or remove the enqueues.
- A-3: utils/art.js targets 4 nonexistent endpoints; body shape {kind,data_url} ≠ backend {image,banner}. Implement the routes or delete art.js (user decision). Paired with BACKEND B-1.
- A-4: LandingPage shows amber "Under Development" badge on Story Forge although the feature is live (cosmetic).
- A-5: WorldAtlas drill-down panel (buildings/NPCs/families per place) not present — WorldCodex is flat; world_nodes.parent_id data is available to build it.
- DOC-1: Root README.md still describes legacy GLM Chat endpoints (/sessions) that don't exist — rewrite when user approves.

## 11. MAINTENANCE RULES
- New component → add §4/§5 entry + any endpoint used to §8.
- New util → §6 entry. New IndexedDB store → bump DB_VERSION + §9 row.
- Any backend call added here MUST exist in BACKEND_MASTER.md §5; if missing, add the route first.
