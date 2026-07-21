# Rubberr Relay Architecture — Phase 0 Spec

**Status:** Design-only. BLOCKING gate for Phase 1. No product code in this document.
**Date:** 2026-07-20 · **Owner:** Justin Johnson · **License target:** Apache-2.0
**Consumes:** `docs/AGENT_PLATFORM_BUILD_PLAN.md` (locked decisions — not re-litigated here).

This spec nails the one open design question from the build plan: **how the relay
carries browser control** so an AI agent on Y6 can drive a *remote user's own,
already-logged-in* Chrome with **no credentials stored server-side** and a
human-in-the-loop hand-back at login / Cloudflare / 2FA gates.

The six Phase-1 build agents (A–F) follow this document. Where a fact could not be
confirmed from the browser-use docs, it is called out explicitly as an **OPEN
QUESTION** rather than guessed — per the owner's rule: one method per function, or a
clean failure; no fallback chains.

---

## 0. Doc facts this spec is grounded on (cited)

From the browser-use documentation, verified 2026-07-20:

- **CDP attach.** `docs/open-source/customize/browser/remote` shows connecting to an
  existing/remote browser via a **CDP URL**:
  `browser = Browser(cdp_url="http://remote-server:9222")`.
  - The public class shown is **`Browser`**, which in current browser-use is an alias
    of **`BrowserSession`**; both accept `cdp_url`. (The build plan wrote
    `BrowserSession(cdp_url=...)`; that is the same constructor. Agent B: prefer
    whichever name the pinned browser-use version exports — **verify at pin time**.)
  - Every `cdp_url` example in the docs is **HTTP** (`http://…:9222`), Chrome's
    standard remote-debugging port. **No `ws://` example is shown.** See §1 OPEN
    QUESTION 1 — this drives the relay's shape.
- **HITL pause/resume.** `docs/customize/hooks` confirms `agent.pause()` and
  `agent.resume()` exist and are called on the agent instance from inside a hook.
  Two hooks are documented: **`on_step_start`** and **`on_step_end`**, both passed to
  `agent.run(...)`. A hook can reach the live browser via
  `agent.browser_session.get_browser_state_summary()` and
  `agent.browser_session.get_or_create_cdp_session()`.
- **Documented HITL pattern (verbatim from the hooks page):**
  ```python
  if '/finished' in current_url:
      agent.pause()
      Path('result.txt').write_text(page_html)
      input('… press [Enter] to resume…')
      agent.resume()
  ```
  This is exactly the primitive the gate handshake in §3 is built on — except we
  replace the blocking `input()` (a local terminal prompt) with a relay round-trip to
  the remote user's companion. **OPEN QUESTION 2:** the docs' example blocks the step
  loop with `input()`; whether `pause()` fully quiesces in-flight CDP calls (vs. just
  gating the *next* step) is not documented. Agent B must confirm behavior against the
  pinned version (see §3.4).

Everything below is consistent with these facts.

---

## 1. Transport — Option A (relay forwards CDP). CONFIRMED VIABLE, with one constraint.

**Decision: Option A ships.** The user's companion launches their real Chrome with
`--remote-debugging-port=9222` and opens **one outbound WebSocket** to the relay. The
relay exposes a **per-user CDP endpoint** that the agent hands to browser-use as
`cdp_url`. This directly generalizes the existing
`rubberr/backend/scrape_existing_browser.py`, which already does
`connect_over_cdp("http://localhost:9222")` against the user's open Stadium tab — we
move the "localhost:9222" to "the relay, tunneled to the user's 9222".

### 1.1 The constraint that shapes the whole relay (READ THIS)

CDP-over-remote is **not** a single WebSocket. A DevTools client (Playwright's
`connect_over_cdp`, and browser-use's `cdp_url`) bootstraps in two steps:

1. **HTTP discovery** — GET `http://<host>:9222/json/version` (and sometimes
   `/json/list`) to read the browser-level **`webSocketDebuggerUrl`**.
2. **WebSocket** — connect to that `webSocketDebuggerUrl` and speak CDP frames.

Therefore the relay's per-user endpoint must proxy **both**: the HTTP discovery JSON
**and** the DevTools WebSocket — and it must **rewrite** the `webSocketDebuggerUrl`
host in the discovery response so it points back at the relay (not at the user's
`localhost:9222`, which the agent cannot reach). This is the single most important
implementation fact for Agent A. A relay that exposes only a bare `ws://` will fail
the discovery step.

### 1.2 What the agent passes

```
cdp_url = "https://relay.rubberr.<domain>/cdp/{session_token}"
```

- The agent (Agent B, on Y6) uses this as `Browser(cdp_url=...)`.
- The relay terminates TLS (Cloudflare in front), authenticates `{session_token}`
  (§2), and multiplexes all CDP traffic for that session over the **companion's single
  outbound tunnel**.
- `/cdp/{token}/json/version` and `/json/list` → relay asks the companion to GET its
  own `localhost:9222/json/*`, returns it with the ws host rewritten to
  `wss://relay…/cdp/{token}/devtools/...`.
- `wss://relay…/cdp/{token}/devtools/browser/<id>` → relay upgrades, and pipes CDP
  frames ↔ companion tunnel ↔ companion's local ws to Chrome.

### 1.3 Companion tunnel multiplexing

The companion opens exactly **one** outbound `wss://relay…/companion/{register_token}`.
All agent-initiated CDP (discovery HTTP + N devtools websockets — browser-use may open
per-target sessions) is multiplexed inside that one tunnel using a framing envelope
(§4.3). This satisfies the plan's "ONE outbound WebSocket from the user's machine" and
keeps the user from ever exposing 9222 to the internet.

### 1.4 OPEN QUESTIONS on transport (must be closed before Agent A/B merge)

- **OQ-1 — Does browser-use accept a raw `ws://`/`wss://` `cdp_url`?** Docs show HTTP
  only. If the pinned version *also* accepts a direct browser-`webSocketDebuggerUrl`,
  the relay could skip HTTP-discovery rewriting and expose only the ws. **Do not design
  for this.** Design the HTTP-facade path (§1.1) because it is what the docs and the
  existing Playwright pattern prove works. If B confirms raw-ws support at pin time,
  it's a simplification to fold in during Phase 2, not a Phase-1 assumption.
- **OQ-2 — Multiple CDP targets over one tunnel.** browser-use may create per-tab/
  per-target CDP sessions (`get_or_create_cdp_session`). The envelope (§4.3) carries a
  `channel` id so >1 concurrent devtools ws can share the tunnel. Confirm browser-use's
  target/session behavior against the pin so `channel` demux is sized right.

### 1.5 Option B (extension high-level actions) — DEFERRED, with why

A browser **extension** that speaks a high-level action namespace (`navigate`,
`click(selector)`, `readDom`, `screenshot`) to the relay — no `--remote-debugging-port`
Chrome launch — is the better long-term UX (no debug-flag Chrome, works on locked-down
machines). **Deferred because:**

1. It throws away the confirmed `cdp_url` reuse of `scrape_existing_browser.py`; we'd
   reimplement browser-use's action layer over a bespoke protocol.
2. browser-use drives via CDP; bolting it onto an extension namespace means either
   re-hosting browser-use logic in the extension (huge) or a lossy CDP↔action shim.
3. MV3 extensions can't attach the debugger silently without `chrome.debugger`
   permission + a visible warning bar anyway, so the "no debug flag" win is partial.

Revisit Option B in a later UX phase once Tier-3 is proven end-to-end on Option A.

---

## 2. Relay auth & session lifecycle (no credentials, ever)

**Principle:** the relay authenticates *tunnels and sessions*, never *user site
credentials*. It never sees a USATT/Stadium password — the user is already logged in
inside their own Chrome; the relay only forwards CDP bytes.

### 2.1 Tokens (two, distinct)

| Token | Issued to | Scope | Lifetime |
|---|---|---|---|
| `register_token` | The companion, out-of-band (user pastes it, or frontend hands it to a locally-launched companion) | "This companion may register as user U" | Long-lived per install; revocable |
| `session_token` | Minted by the relay when a companion opens a session | "This one CDP session for user U's browser" | Single session; dies on stop/timeout |

- No account system is required for Tier-1/3 to function; a `register_token` is an
  opaque high-entropy string bound to a `user_id` in the relay's in-memory (or small
  KV) session registry. **No passwords, no site cookies, no OpenRouter key** are stored
  in that registry.
- The **agent** authenticates to the relay's `/cdp/{session_token}` endpoint with the
  `session_token` only. It cannot enumerate other users' sessions (one token = one
  session = one browser).

### 2.2 Lifecycle

```
register  companion --WS connect--> relay/companion/{register_token}
                                     relay: validate token -> user_id, mark ONLINE
start     agent (or frontend) --POST relay/session/start {register_token or user_id}
                                     relay: mint session_token, bind to that companion
                                     relay: one browser per user — if a live session
                                            exists for user_id, REJECT (409) unless
                                            ?takeover=true which stops the old one first
attach    agent Browser(cdp_url=relay/cdp/{session_token}) -> CDP flows over tunnel
gate      see §3
stop      agent --POST relay/session/stop {session_token}   (or run completes)
                                     relay: tear down channels, drop session_token
timeout   relay: idle >IDLE_TTL or total >MAX_TTL -> force stop, notify companion
cleanup   companion WS closes -> relay stops any bound session, frees user slot
```

- **One browser per user** — enforced at `session/start` (409 on conflict). No implicit
  second session.
- **Timeouts (defaults; Phase-2 config):** `IDLE_TTL = 120s` no CDP frames →
  `SESSION_ENDED{reason:"idle_timeout"}`; `MAX_TTL = 15min` hard cap;
  `GATE_TTL = 5min` unsolved gate (see §3.3). All are clean errors, no retries.
- **Cleanup is idempotent** and driven by tunnel close: if the companion drops, the
  relay reaps the session immediately (see §7).

---

## 3. The `wait_for_human` gate handshake

When the agent hits a login page, Cloudflare interstitial, captcha, or 2FA prompt, it
must **stop touching the browser**, ask the *remote user* to solve it in their own
Chrome, and resume only when the user says "done". Built on the documented
`agent.pause()` / `agent.resume()` primitive (§0).

### 3.1 Gate detection (Agent B, in an `on_step_start` hook)

The hook inspects the browser state (URL + a cheap DOM/text signal already available
via `get_browser_state_summary()`) for gate signatures:

- URL/host on a known login path, or Cloudflare `challenges.cloudflare.com` /
  `__cf_chl` / "Verify you are human" text,
- a visible OTP/2FA input, or a captcha iframe (hCaptcha/Turnstile/reCAPTCHA).

Detection lives in Agent B (**not** the relay — the relay must stay content-blind,
§5). The relay only routes the resulting signal.

### 3.2 Message flow (happy path)

```
Agent B (Y6)                 Relay                      Companion (user machine)      User
   |  detect gate               |                              |                        |
   |  agent.pause()             |                              |                        |
   |  POST /session/gate  ----> | GATE_OPEN ----------------->  | show prompt --------->  | sees "Log in / solve, then Continue"
   |  (gate_id, kind, hint)     | (relay only relays, no page  |                        |
   |                            |  content required)           |                        | solves it IN THEIR OWN BROWSER
   |                            |                              | user clicks Continue    |
   |                            | <---------------- GATE_CLEARED (gate_id)               |
   |  <---- gate resolve  ------ |                              |                        |
   |  (poll or push, gate_id)   |                              |                        |
   |  agent.resume()            |                              |                        |
   |  ...continues scrape       |                              |                        |
```

- The **user solves the gate directly in their own Chrome tab** — the same tab the
  agent is attached to. Nothing about the credential/OTP passes through the agent or
  relay; only the *fact* "gate cleared" (a `gate_id`) travels back.
- Agent B stays paused (no CDP writes) for the whole window. `on_step_start` returning
  while paused means the step loop is gated by browser-use's own pause state.

### 3.3 Timeout / abandonment

If no `GATE_CLEARED` within `GATE_TTL` (default 5min): relay emits
`GATE_TIMEOUT{gate_id}` to the agent, agent does **not** resume — it ends the run with
a clean `GateNotSolved` error surfaced to Agent F → frontend ("You didn't finish the
login; nothing was scraped. Try again."). **No fallback, no auto-solve, no captcha
service.** (The 2captcha MCP present in this workspace is explicitly NOT used for
Tier-3 — the whole point is human-in-the-loop with the user's own session.)

### 3.4 OPEN QUESTION — pause granularity (OQ-3)

The docs' HITL example blocks with `input()` *inside* the hook, which implies the hook
itself holds the loop. Our design instead returns from the hook after `pause()` and
resumes on an async relay signal. Agent B must confirm against the pinned version that:
(a) `pause()` prevents the *next* step's actions from firing, and (b) resuming is safe
from an async callback (not only from within the same hook frame). If (b) is false, the
fallback-free implementation is to **keep the hook blocking** on an `asyncio.Event`
that the relay listener sets on `GATE_CLEARED` — still one method, still clean.

---

## 4. Message schemas (JSON, both directions)

All relay messages are JSON objects with a `type` and a monotonic `seq`. Transport is
the companion tunnel WS (§1.3) and the agent's control calls (`/session/*` POST +
a `GET /session/events` SSE or WS for push-back). Field names are normative — A, B, C
must not drift.

### 4.1 Control envelope (common)

```json
{ "type": "<UPPER_SNAKE>", "seq": 42, "session_id": "s_9f3…", "ts": 1721500000.12 }
```

### 4.2 Companion ⇄ Relay (registration & lifecycle)

```json
// Companion -> Relay, on tunnel open
{ "type": "REGISTER", "register_token": "rt_…", "companion_version": "0.1.0",
  "chrome_debug_port": 9222, "platform": "win32" }

// Relay -> Companion
{ "type": "REGISTER_OK", "user_id": "u_123", "heartbeat_interval_s": 20 }
{ "type": "REGISTER_REJECT", "reason": "bad_token" }

// Relay -> Companion  (a session was started for this companion)
{ "type": "SESSION_START", "session_id": "s_9f3…" }

// Relay -> Companion / Companion -> Relay
{ "type": "HEARTBEAT" }

// Relay -> Companion
{ "type": "SESSION_ENDED", "session_id": "s_9f3…",
  "reason": "completed | idle_timeout | max_timeout | gate_timeout | agent_error | companion_gone | takeover" }
```

### 4.3 CDP tunnel frames (Companion ⇄ Relay, carrying agent CDP)

The relay wraps every proxied CDP interaction in this envelope so one tunnel carries
HTTP discovery + N devtools channels:

```json
// Relay -> Companion: proxy an HTTP discovery GET
{ "type": "CDP_HTTP_REQ", "req_id": "h1", "path": "/json/version" }
// Companion -> Relay: raw JSON body from localhost:9222 (companion does NOT rewrite;
// the RELAY rewrites webSocketDebuggerUrl host before returning to the agent)
{ "type": "CDP_HTTP_RES", "req_id": "h1", "status": 200, "body": { "...": "..." } }

// Relay -> Companion: open a devtools ws channel to a target
{ "type": "CDP_WS_OPEN", "channel": 1, "target_ws_path": "/devtools/browser/<id>" }
{ "type": "CDP_WS_OPEN_OK", "channel": 1 }

// Bi-directional: one CDP protocol frame (already JSON per CDP)
{ "type": "CDP_WS_FRAME", "channel": 1, "data": { "id": 7, "method": "Page.navigate", "params": {"url":"…"} } }

// Either side closes a channel
{ "type": "CDP_WS_CLOSE", "channel": 1, "code": 1000 }
```

> Note: `data` payloads are opaque CDP JSON the relay **forwards without inspecting**
> (§5). The relay parses only the discovery response, and only to rewrite the ws host.

### 4.4 Gate handshake schema

```json
// Agent B -> Relay
{ "type": "GATE_OPEN", "session_id": "s_9f3…", "gate_id": "g_01",
  "kind": "login | cloudflare | captcha | twofa | unknown",
  "hint": "Log in to Stadium, then click Continue",
  "url_host": "stadiumcompete.com" }        // host only — never full URL w/ tokens/query

// Relay -> Companion (verbatim passthrough of the human-facing fields)
{ "type": "GATE_OPEN", "gate_id": "g_01", "kind": "login", "hint": "…", "url_host": "stadiumcompete.com" }

// Companion -> Relay  (user clicked Continue)
{ "type": "GATE_CLEARED", "gate_id": "g_01" }

// Relay -> Agent B
{ "type": "GATE_CLEARED", "gate_id": "g_01" }

// Relay -> Agent B (and Companion), on expiry
{ "type": "GATE_TIMEOUT", "gate_id": "g_01" }
```

`url_host` is host-only by policy (§5 / privacy rule: no tokens or PII in URLs).

---

## 5. Security boundaries

**What the relay CAN see:**
- Tunnel/session metadata: `user_id`, tokens, timestamps, heartbeats, gate `kind`/
  `url_host`, byte counts.
- The CDP **discovery** JSON (`/json/version`) — enough to rewrite `webSocketDebuggerUrl`.

**What the relay CANNOT / MUST NOT see or store:**
- **No site credentials** — the user logs in themselves; passwords/OTP never leave the
  user's browser.
- **No OpenRouter key** — it goes frontend → Agent B only (§6); it never transits the
  relay path.
- **Page content is opaque.** `CDP_WS_FRAME.data` is forwarded byte-for-byte; the relay
  does not parse, log, or persist DOM/screenshots/response bodies. (Frames are
  *transported*; they are not *inspected*. If debug logging is ever added it MUST redact
  `CDP_WS_FRAME.data`.)
- **No full URLs with query strings** in any relay-visible field — host only, per the
  privacy rule (tokens/PII often ride in query params).

**Isolation & exposure:**
- **Per-user isolation:** one `session_token` ⇒ one companion ⇒ one browser. A token
  cannot address another user's tunnel. Sessions are keyed by `user_id`; channel demux
  is per-session.
- **9222 is never exposed to the internet.** The user's Chrome listens only on
  `localhost:9222`; the sole network egress is the companion's outbound WS to the relay.
  Inbound remote-debugging is impossible by construction.
- **CDP endpoint not public:** `/cdp/{session_token}` is unguessable + single-session +
  Cloudflare-fronted. There is no public `:9222` and no relay port a scanner can attach
  a debugger to.
- **Agent-side blast radius:** Agent B on Y6 can drive whatever tab the user has open —
  so Agent B's prompt/actions are scoped to the target site task, and the companion UI
  makes clear the agent is active (Phase-1 Agent C requirement).

---

## 6. Where the LLM lives (Gemini via OpenRouter — agent side only)

- **All** Gemini/OpenRouter calls happen **inside Agent B on Y6**, via browser-use's
  LLM config (`base_url=https://openrouter.ai/api/v1`, slug e.g.
  `google/gemini-3-pro-preview` / Flash tier).
- **BYOK key path (confirmed from existing code):** the frontend already sends a
  user-supplied key in the **`X-User-Api-Key`** header (`main.py: _get_user_ai_key`);
  today it feeds Anthropic. For Tier-3 the **same header carries the user's OpenRouter
  key**: frontend (BYOK input, already in `DemoBar`) → Agent F `/chat`|`/tools/*` →
  Agent F hands it to Agent B as a call argument (§6.1) → browser-use LLM client. It is
  used in-process and **not persisted** and **never sent to the relay**.
- The relay carries **zero** LLM traffic. Gemini sees page content only because Agent B
  (which holds the CDP session) feeds it — that content reaches Agent B over the tunnel,
  but the *relay* never inspects it (§5).

**OPEN QUESTION OQ-4:** header naming. Existing code uses one `X-User-Api-Key` for "the
AI key". If a user supplies *both* an Anthropic key (NL layer, `ai_handler.py`) and an
OpenRouter key (browser agent), Agent E/F must decide: reuse the one header and route
by which tool is called, or add `X-User-OpenRouter-Key`. Flagged for E↔F to settle in
Phase 1; not guessed here.

---

## 7. Failure modes (each a clean, single-path failure — no fallback chains)

| # | Failure | Detected by | Defined behavior |
|---|---|---|---|
| F1 | **Companion disconnects mid-scrape** | Relay: tunnel WS close / missed heartbeats (`2× heartbeat_interval`) | Relay force-stops the session, emits `SESSION_ENDED{reason:"companion_gone"}` to Agent B. B aborts the run and returns a clean `CompanionDisconnected` error to F → UI: "Your browser link dropped; nothing partial was saved. Reconnect and retry." No auto-reconnect-and-resume. |
| F2 | **Gate never solved (timeout)** | Relay `GATE_TTL` | `GATE_TIMEOUT` → B does **not** resume, ends run with `GateNotSolved`. UI tells user to retry. No captcha-solver fallback. (§3.3) |
| F3 | **CDP connection drops** (Chrome closed/crashed, tab navigated away, ws error) | Agent B: CDP call raises / channel `CDP_WS_CLOSE` unexpected | B ends the run with `CdpLost`; relay reaps session. UI: "Lost the browser connection." No silent reconnect loop. |
| F4 | **OpenRouter error** (401 bad key, 429, 5xx, model unavailable) | Agent B: LLM call raises | B **fails loudly** (matches existing `/chat` "FAIL LOUDLY, no friendly fallback" policy) with `LlmError` incl. status; F surfaces it verbatim-ish to UI ("OpenRouter rejected the key / rate-limited"). No model fallback, no retry storm — one clean surfaced error. |
| F5 | **Two sessions for one user** | Relay `session/start` | 409 `SessionConflict` unless explicit `?takeover=true` (which `SESSION_ENDED{reason:"takeover"}`s the old one first). Never two silently. |
| F6 | **Relay unreachable from agent** | Agent B: connect to `cdp_url` fails | Clean `RelayUnreachable` before any scrape; F → UI. No local-browser fallback (there is no local browser on Y6). |
| F7 | **Idle / max session TTL** | Relay timers | `SESSION_ENDED{reason:"idle_timeout"|"max_timeout"}`; B ends cleanly. |

All errors propagate as typed exceptions from Agent B → Agent F → a single JSON error
shape on `/chat`|`/tools/*` (`{"error": {"type": "...", "detail": "..."}}`), consistent
with the existing loud-failure convention in `main.py`.

---

## 8. Interface contract: Agent B (`browser_agent.py`) ↔ Agent F (backend surface)

This is the **frozen signature** so B and F build in parallel without drift. Agent B
owns `rubberr/backend/browser_agent.py`; Agent F owns `main.py` + `ai_handler.py` and
calls **only** the functions below.

### 8.1 Primary entry point (async)

```python
# rubberr/backend/browser_agent.py  (Agent B owns this file)

async def run_browser_task(
    *,
    task: str,                     # natural-language goal for the agent, e.g.
                                   #   "Scrape my Stadium singles match set-scores"
    site: str,                     # "stadium" | "usatt" | "omnipong"  (enum-validated)
    player_name: str,              # parameterized — NO hardcoded "Justin"; required
    session_token: str,            # relay CDP session token -> cdp_url is built from this
    openrouter_key: str,           # BYOK; used in-process only, never logged/persisted
    model: str = "google/gemini-3-pro-preview",
    relay_base_url: str,           # e.g. "https://relay.rubberr.<domain>"
    on_gate: "GateCallback | None" = None,   # optional push hook for gate UI; see 8.3
    max_steps: int = 40,
) -> "BrowserTaskResult":
    ...
```

### 8.2 Return type (frozen shape)

```python
@dataclass
class BrowserTaskResult:
    status: str                    # "ok" | "gate_timeout" | "companion_gone"
                                   #      | "cdp_lost" | "llm_error" | "relay_unreachable"
    matches: list[dict]            # normalized records (schema below); [] on failure
    steps_used: int
    error: dict | None             # {"type": "...", "detail": "..."} when status != "ok"
```

**Normalized `matches[]` record** (reuses `stadium_league_scraper.py` parse/normalize;
must match what the frontend ledger + DB expect — `source ∈ {omnipong, stadium,
stadium_league}`):

```json
{
  "source": "stadium",
  "player_name": "Ada Lovelace",
  "opponent": "Grace Hopper",
  "date": "2026-05-11",
  "result": "W",
  "match_score": "3-1",
  "set_scores": ["11-8","9-11","11-6","11-7"],
  "event": "Spring Open — U1800"
}
```

Agent B returns this shape; Agent F is responsible for **writing it** (DB for the public
feed / passing to the frontend for IndexedDB in Tier-3) — **B does not touch the DB.**
This keeps the "B scrapes, F persists" boundary clean and matches the existing
`sync_stadium` pattern where `main.py` orchestrates and the scraper returns data.

### 8.3 Gate callback (optional push to UI)

```python
# Called by Agent B when a gate opens/clears, so F can push status to the frontend.
GateEvent = TypedDict("GateEvent", {
    "event": str,        # "gate_open" | "gate_cleared" | "gate_timeout"
    "gate_id": str,
    "kind": str,         # login | cloudflare | captcha | twofa | unknown
    "hint": str,
    "url_host": str,
})
GateCallback = Callable[[GateEvent], Awaitable[None]]
```

If `on_gate` is `None`, Agent B still performs the full relay gate handshake (§3) — the
callback is purely for surfacing gate state to the user's frontend, not for control.

### 8.4 What F must NOT do / assume

- F never builds `cdp_url` itself or talks CDP — it passes `session_token` +
  `relay_base_url`; B owns all browser-use/relay wiring.
- F never sees the OpenRouter key beyond forwarding it into `run_browser_task`.
- F treats `BrowserTaskResult.status != "ok"` as the single error surface (§7) and does
  not retry with a different method.

---

## 9. Full Tier-3 private-sync sequence (ASCII)

```
 USER            COMPANION (user machine)        RELAY (Y6)                 AGENT B (Y6, browser-use+Gemini)      BACKEND F (Y6)        FRONTEND (CF Pages, user's browser)
  |                     |                            |                              |                                   |                        |
  | click "Sync my Stadium data"  ------------------------------------------------------------------------------------------------------------>|
  |                     |                            |                              |                          POST /tools/sync/stadium         |
  |                     |                            |                              |                          (X-User-Api-Key: OpenRouter BYOK)|
  |                     |                            |                              |   run_browser_task(site="stadium",                        |
  |                     |                            |                              |     player_name=…, session_token=…, openrouter_key=…)     |
  | launch companion    |                            |                              |                                   |                        |
  |-------------------->| Chrome --remote-debugging-port=9222 (localhost only)      |                                   |                        |
  |                     | open ONE outbound WS ---> /companion/{register_token}     |                                   |                        |
  |                     |   REGISTER ------------->  | validate -> user_id, ONLINE  |                                   |                        |
  |                     |   <----------- REGISTER_OK |                              |                                   |                        |
  |                     |                            | <---- POST /session/start ---|  (B or F starts session)          |                        |
  |                     |   <------- SESSION_START -- | mint session_token           |                                   |                        |
  |                     |                            |                              | Browser(cdp_url=relay/cdp/{token})|                        |
  |                     |                            | <== CDP_HTTP_REQ /json/version|  (browser-use discovery)         |                        |
  |                     |  GET localhost:9222/json/version                          |                                   |                        |
  |                     |   ==> CDP_HTTP_RES {webSocketDebuggerUrl…} ==>  relay rewrites host -> wss://relay/cdp/{token}/devtools/...          |
  |                     |                            | <== CDP_WS_OPEN channel=1 ===|                                   |                        |
  |                     |  local ws -> Chrome 9222    |  <==== CDP_WS_FRAME ====>     |  agent drives the real tab        |                        |
  |                     |                            |                              |  navigate to Stadium matches      |                        |
  |                     |                            |                              |                                   |                        |
  |                     |            === GATE (Cloudflare / login / 2FA) HIT ===                                        |                        |
  |                     |                            |                              |  on_step_start: detect gate       |                        |
  |                     |                            |                              |  agent.pause()                    |                        |
  |                     |                            | <---- GATE_OPEN (g_01) -------|  POST /session/gate               |                        |
  |                     |   <------- GATE_OPEN g_01 --| (kind, hint, url_host)        |  --- on_gate(gate_open) ------------------------------> push "Solve login" to UI
  |  solve login/2FA IN OWN CHROME (relay never sees creds)                          |                                   |                        |
  |<------------------->| user completes in the same tab                            |                                   |                        |
  |  click "Continue"   |                            |                              |                                   |                        |
  |-------------------->|   GATE_CLEARED g_01 ----->  | ---- GATE_CLEARED g_01 ----->|  agent.resume()                   |                        |
  |                     |                            |                              |  continue scrape (DOM-tree first) |                        |
  |                     |  <==== CDP_WS_FRAME ====>    |  <==== CDP_WS_FRAME ====>     |  read match cards + set scores    |                        |
  |                     |                            |                              |  build normalized matches[]       |                        |
  |                     |                            | <---- POST /session/stop -----|  return BrowserTaskResult(ok)     |                        |
  |                     |   <------ SESSION_ENDED --- |  reap channels               | -----> matches[] -----------------> F: hand to frontend    |
  |                     |                            |                              |                                   |  matches[] (NOT written    |
  |                     |                            |                              |                                   |   to server DB for Tier-3) |
  |  see my matches  <------------------------------------------------------------------------------------------------------ store in IndexedDB, render
  |                     |                            |                              |                                   |                        |
```

Gate-timeout / disconnect variants follow §7 (agent ends clean, `SESSION_ENDED` with
the matching `reason`, UI shows a single clear error — nothing partial persisted).

---

## 10. Open questions summary (close before Phase-1 merge)

- **OQ-1** — Does the pinned browser-use accept a raw `ws://` `cdp_url`? Docs show HTTP
  only; design the HTTP-facade relay regardless (§1.1/§1.4). Simplify later if confirmed.
- **OQ-2** — browser-use target/session model over one tunnel: how many concurrent CDP
  channels? Sizes the `channel` demux (§1.4/§4.3).
- **OQ-3** — `pause()` granularity + async `resume()` safety vs. the docs' blocking
  `input()` example (§3.4). Determines push-signal vs. blocking-Event impl.
- **OQ-4** — one `X-User-Api-Key` header vs. a separate `X-User-OpenRouter-Key` when a
  user supplies both an Anthropic and an OpenRouter key (§6). E↔F to settle.
- **`Browser` vs `BrowserSession`** — same constructor/alias; pin-time verify which name
  the version exports (§0).

None of these block writing the Phase-1 code skeletons; each is a small, bounded check
Agent B runs against the pinned browser-use before the A/B integration point.
```
