# Rubberr Agent Platform — Unified Build Plan

**Goal:** turn the existing Rubberr/OmniPong code into one product that anyone can use:
type your name → find your real USATT rating + tournaments → optionally let an AI
agent drive *your own logged-in browser* to pull your private match data — **no
passwords ever stored on our servers.** Efficient, no real bugs, reviewed in depth,
unified, solidified before it ships.

Date: 2026-07-20 · Owner: Justin Johnson · License target: Apache-2.0

---

## 0. Decisions already locked (do not re-litigate)

- **Browser-driving engine:** [`browser-use`](https://docs.browser-use.com) (Python, MIT).
  Chosen after head-to-head research — only framework with documented CDP-attach
  (`BrowserSession(cdp_url=...)`), HITL `agent.pause()/resume()`, and OpenRouter/Gemini
  support all confirmed. Runner-up Stagehand (TS); Skyvern HITL is Enterprise-gated;
  Nova Act fails OpenRouter; Claude-in-Chrome has no API (Claude-only, subscription-gated).
- **Brain:** Google **Gemini via OpenRouter** (`base_url=https://openrouter.ai/api/v1`,
  slug `google/gemini-3-pro-preview` or Flash tier), using the **user's own OpenRouter key**
  (the `DemoBar` BYOK plumbing already exists in the frontend).
- **Transport:** **OpenClaw-style relay** — a single outbound WebSocket from the user's
  machine to a relay server, so the agent (on Y6) can drive the user's own browser without
  the user exposing a CDP port to the internet. This is the connective tissue that makes it
  multi-tenant.
- **No stored credentials.** The user logs in themselves; the agent drives the
  already-authenticated tab. At any gate (Cloudflare / 2FA / captcha) the agent PAUSES and
  hands back to the user, then resumes.
- **Storage:** private per-user scraped data lives in the **user's browser (IndexedDB)**,
  never our DB. Only the *global public* tournament feed lives server-side.
- **Hosting:** Y6 (Windows, Tailscale) runs the always-on public scraper + the relay server;
  Cloudflare Pages serves the Rubberr frontend; Cloudflare fronts the relay/API.
- **Off Render entirely.**

## Three tiers (what "reusable by anyone" means)

| Tier | What | Login? | Where it runs |
|---|---|---|---|
| **1. Public lookup** | name → USATT rating/history/tournaments | none | real browser via relay (USATT is Cloudflare-walled to plain fetch) |
| **2. Global feed** | always-on crawl of omnipong.com public tournaments/leagues across states | our (owner) login | Y6 scraper, read-only API |
| **3. Private sync** | user's own Stadium/USATT match data | user logs in themselves | relay → user's own browser, agent drives it, data → their IndexedDB |

---

## Existing assets to REUSE (verified — do not rebuild from scratch)

- `omnipong_scraper.py` + `browser_manager.py` — omnipong.com login + tournament/match scrape (Playwright persistent context). **Feeds Tier 2.**
- `rubberr/backend/scrape_existing_browser.py` — already does `connect_over_cdp` to the user's open browser and scrapes the logged-in Stadium tab. **This is the Tier-3 seed pattern** — browser-use generalizes it (drops the hardcoded `.MatchCard` selectors, adds vision + HITL + Gemini).
- `rubberr/backend/stadium_league_scraper.py` — Stadium parse + DB-write logic (reuse the parsing/normalization, drop the stored-password headless login).
- `rubberr/backend/ai_handler.py` — LLM intent parse (Claude) + Whisper. Keep as the NL layer.
- `rubberr/backend/main.py` — FastAPI `/chat` + `/tools/*` agent surface. **Remove** the `/credentials` stored-password path.
- Rubberr Next.js frontend (11 pages: ChatAgent, settings, scoreboard, tournaments, analytics, map).
- DB schema (matches, rating_history, tournaments, players; `source` in {omnipong, stadium, stadium_league}).

**Kill:** the fabricated `demos/omnipong/index.html` (reimplemented matcher — padding). OmniPong is Rubberr's capability layer, not a separate demo.

---

## Phased plan (with review gates)

### Phase 0 — Architecture spec (1 agent, BLOCKING, no code)
Produce `docs/RELAY_ARCHITECTURE.md` nailing the one open design question:
**how the relay carries browser control.**
- **Recommended default (Option A):** relay forwards CDP. User's lightweight companion
  launches Chrome with `--remote-debugging-port=9222` and opens ONE outbound WS to the relay;
  relay exposes a per-user CDP ws endpoint; `browser-use` connects via `cdp_url`. Reuses the
  existing `connect_over_cdp` pattern directly.
- **Later-UX (Option B):** browser extension speaks a high-level action namespace to the relay
  (no debug-flag Chrome launch). More work; defer.
- Define: relay auth (per-user token, no creds), session lifecycle, the `wait_for_human` gate
  handshake, message schema, and where Gemini/OpenRouter calls happen (agent side, never relay).
- **Gate:** owner review before any Phase-1 code.

### Phase 1 — Build (parallel, STRICT file ownership to avoid collisions)
All work is inside the one git root `~/Desktop/omnipong`, so ownership must be disjoint.

- **Agent A — Relay server** (`relay/` new dir). WS relay, per-user token auth, session
  registry, CDP forwarding, `wait_for_human` pause/resume signaling. Runs on Y6.
- **Agent B — Browser-agent core** (`rubberr/backend/browser_agent.py` new). Wraps `browser-use`:
  attaches via `cdp_url` (through relay), Gemini-via-OpenRouter brain, `pause()/resume()` on gates,
  parameterized per-player. Generalizes `scrape_existing_browser.py` for omnipong/Stadium/USATT.
- **Agent C — User companion** (`companion/` new dir). Tiny local launcher: opens the user's
  Chrome with remote-debugging, dials the relay, shows gate prompts ("log in / solve this, then
  continue"). Cross-platform (Win for Y6-adjacent users + Mac).
- **Agent D — Tier-2 always-on feed** (`feed/` new dir + reuse `omnipong_scraper.py`). Scheduled
  omnipong.com crawl → sanitized public tournament DB → read-only API. Runs on Y6.
- **Agent E — Frontend + ledger** (`rubberr/frontend/` only). USATT name-lookup UI, IndexedDB
  local ledger, sync button wired to the relay flow, remove the stored-password settings path,
  BYOK OpenRouter key input. Owns frontend exclusively.
- **Agent F — Backend surface** (`rubberr/backend/main.py`, `ai_handler.py`). Remove `/credentials`;
  wire `/chat` + `/tools/*` to call `browser_agent.py`; keep DB-write/parse from
  `stadium_league_scraper.py`. **Coordinates with B on the interface (defined in Phase 0 spec).**

### Phase 2 — Integration & unification (1 agent, BLOCKING)
Wire A–F into one runnable path: companion → relay → browser-agent → ledger/DB → frontend.
Single config, single `.env.example`, one `run.sh` per host (Y6 vs user). Resolve any interface
drift. Apache-2.0 + NOTICE. Delete dead/duplicate paths. No parallel work here.

### Phase 3 — In-depth review (parallel adversarial, BLOCKING)
Independent reviewers, each trying to BREAK it, most-severe-first:
- **Security:** no creds stored anywhere; relay token scoping; no arbitrary code exec; IndexedDB
  data can't leak cross-user; OpenRouter key never leaves the user's browser except to OpenRouter.
- **Correctness:** the HITL pause/resume actually survives a real Cloudflare gate; per-player
  parameterization has no "Justin" leaks; DB/ledger schema matches what the UI reads.
- **Efficiency:** token cost of the vision loop (prefer DOM-tree actions over screenshot-coordinate
  clicking); no redundant re-scrapes; sync pulls deltas only.
- Every finding verified before it's accepted; fixes re-reviewed.

### Phase 4 — Real smoke test (owner-in-the-loop, cannot be faked)
Per house rules — unit tests are NOT proof. Exercise the real path:
1. Start relay on Y6 + companion locally.
2. Real Chrome, user logs into Stadium themselves.
3. Agent (Gemini via OpenRouter) drives the real tab, hits a gate, pauses, user solves, resumes,
   scrapes real matches → real IndexedDB ledger → Rubberr UI shows them.
4. Measure: time-to-first-scrape, token cost, gate-handoff latency. Report what was NOT verified.

---

## Unblockers needed from owner (before Phases 2/4)

1. **Y6 access** — SSH key + Windows username (relay + Tier-2 feed run there).
2. **OpenRouter key** available for the real smoke test (user-supplied at runtime; owner's for testing).
3. **Rotate OmniPong `.env` keys** (Anthropic/OpenAI/ElevenLabs/Deepgram/Twilio seen in plaintext).

## Definition of done
One command brings up the platform per host. Any visitor can look up their USATT rating with no
login; a user can pull their private Stadium data through their own browser with nothing stored on
our side; every function reviewed, no known real bugs, one unified codebase, Apache-2.0.
