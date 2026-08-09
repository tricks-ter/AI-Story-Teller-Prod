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
- Alt hosts: render.yaml, start.sh. CI tests: .github/workflows/tests.yml (pytest api/tests -q).

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
