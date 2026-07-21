# Rubberr Relay

Phase 1, Agent A of the Rubberr Agent Platform. Implements
[`docs/RELAY_ARCHITECTURE.md`](../docs/RELAY_ARCHITECTURE.md) §1 (transport),
§2 (auth/lifecycle), §3 (gate routing), §4 (message schemas), §5 (security),
§7 (failure modes).

The relay is the one piece of infrastructure that lets an AI agent (running
on Y6) drive a **remote user's own, already-logged-in Chrome**, with **no
credentials ever stored server-side**, and a human-in-the-loop hand-back at
login/Cloudflare/2FA gates. It never sees page content, never sees
passwords, and never sees the OpenRouter key.

## What's in this directory

| File | Purpose |
|---|---|
| `server.py` | The FastAPI/ASGI app — every route and websocket handler. |
| `registry.py` | In-memory state: companions, sessions, gates. No external DB. |
| `protocol.py` | Wire message `type` string constants (normative names from §4). |
| `errors.py` | One exception type per clean failure mode (§7); no fallback chains. |
| `config.py` | All tunables read from env vars, with documented defaults. |
| `register_tokens.example.json` | Copy to `register_tokens.json` and fill in real tokens. |
| `test_relay.py` | Self-check — runs the real ASGI app end-to-end, no browser needed. |
| `run.sh` | Creates a venv, installs deps, starts the relay. Works on Windows (Git Bash/WSL) and Mac. |

## How the CDP HTTP-facade + multiplex works (§1.1 — the load-bearing detail)

Chrome DevTools Protocol over a remote connection is **not** a single
websocket. A client (browser-use / Playwright's `connect_over_cdp`) does two
things:

1. `GET http://host:9222/json/version` (or `/json/list`) to read the
   browser's `webSocketDebuggerUrl`.
2. Opens that `webSocketDebuggerUrl` and speaks CDP frames.

The user's Chrome only listens on `localhost:9222` and never touches the
network directly. The **companion** (a small process on the user's machine,
built by Agent C) opens exactly **one** outbound `wss://relay/companion/{register_token}`
tunnel and does the actual `localhost:9222` calls on the relay's behalf. The
relay:

- Exposes `GET /cdp/{session_token}/json/version` and `/json/list`. On a hit,
  it sends a `CDP_HTTP_REQ` envelope down the companion tunnel, the companion
  does the real `GET localhost:9222/json/version` and replies with
  `CDP_HTTP_RES{status, body}`. The relay then **rewrites** every
  `webSocketDebuggerUrl` in that body — swapping `ws://localhost:9222/devtools/...`
  for `wss://<relay-host>/cdp/{session_token}/devtools/...` — and returns the
  rewritten JSON to the agent. This is the *only* field the relay parses;
  everything else in the discovery body passes through untouched.
- Exposes `WS /cdp/{session_token}/devtools/{target_path:path}`. When the
  agent connects here (using the URL it just got back from discovery), the
  relay allocates a `channel` number on the companion, sends
  `CDP_WS_OPEN{channel, target_ws_path}` down the tunnel, waits for
  `CDP_WS_OPEN_OK`, then bridges: every text frame from the agent is wrapped
  as `CDP_WS_FRAME{channel, data}` and sent down the tunnel; every
  `CDP_WS_FRAME{channel, data}` the companion sends back is unwrapped and
  forwarded to the matching agent websocket. Multiple concurrent devtools
  targets (browser-use may open more than one CDP session) get distinct
  channel numbers over the *same* companion tunnel — this is the
  multiplexing §1.3/§4.3 calls for.
- `CDP_WS_FRAME.data` is forwarded **without inspection** (§5): the relay's
  only touch on that payload is the `json.loads`/`json.dumps` needed to fit
  it into the envelope for multiplexing — no field of the decoded CDP
  message is read, logged, or branched on anywhere in `server.py`.

## Session lifecycle, gates, timeouts

- `POST /session/start {register_token | user_id, takeover?}` — mints a
  `session_token`, binds it to the caller's online companion, enforces
  one-browser-per-user (`409 SessionConflict` unless `?takeover=true`).
- `POST /session/stop {session_token}` — tears the session down cleanly,
  closes every open devtools channel, notifies the companion.
- `POST /session/gate {session_token, gate_id, kind, hint, url_host}` —
  Agent B calls this when it detects a login/Cloudflare/2FA/captcha wall and
  has already called `agent.pause()`. The relay forwards `GATE_OPEN`
  verbatim to the companion (which shows the user a prompt) and does not
  interpret `hint`/`url_host` beyond forwarding — `url_host` is host-only by
  policy, never a full URL with query params/tokens.
- `GET /session/events/{session_token}` — SSE push channel for
  `GATE_CLEARED` / `GATE_TIMEOUT` / `SESSION_ENDED`.
- `GET /session/gate/{session_token}/{gate_id}/wait` — a bounded long-poll
  alternative to the SSE stream for callers that prefer request/response;
  backed by the same `asyncio.Event`, not a second implementation.
- Timeouts, all clean single-path failures (§7), no retries: `IDLE_TTL`
  (120s default, no CDP frames) → `SESSION_ENDED{reason:"idle_timeout"}`;
  `MAX_TTL` (15 min) hard cap; `GATE_TTL` (5 min) unsolved gate →
  `GATE_TIMEOUT` to both sides, agent does not resume.

## Running it

```bash
cd relay
cp register_tokens.example.json register_tokens.json
# edit register_tokens.json: {"rt_<high-entropy>": "u_<user id>"}
./run.sh
```

`run.sh` creates `.venv/` next to this file, installs `requirements.txt`
into it, and starts uvicorn on `0.0.0.0:8765` (override with `RELAY_PORT`).
It detects Windows venvs (`.venv/Scripts/python.exe`) vs POSIX venvs
(`.venv/bin/python`) automatically, so the same script runs on Y6 (Windows,
via Git Bash) and on a Mac dev machine.

Config is all environment variables (see `config.py` for the full list and
defaults): `RELAY_HOST`, `RELAY_PORT`, `RELAY_IDLE_TTL_S`, `RELAY_MAX_TTL_S`,
`RELAY_GATE_TTL_S`, `RELAY_HEARTBEAT_INTERVAL_S`,
`RELAY_COMPANION_RPC_TIMEOUT_S`, `RELAY_REGISTER_TOKENS_FILE`.

### Self-check (no browser, no Y6, no companion process needed)

```bash
cd relay
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m pytest test_relay.py -v
```

This drives the **real** ASGI app (`server.app`) through Starlette's
`TestClient` — real WebSocket handshakes, real HTTP requests, real asyncio
timers — playing the companion role itself over the wire (exactly the
messages a real companion process would send) so every relay code path
actually executes: register → reject-bad-token → session/start (incl. the
409 one-per-user conflict) → CDP discovery GET + `webSocketDebuggerUrl`
rewrite → devtools websocket open + a fake CDP frame round trip → gate
open/clear → session/stop → gate timeout. See `test_relay.py`'s module
docstring for exactly what this does and does not prove.

## Security posture (§5), concretely

- No site credentials, ever. The relay only ever proxies bytes between an
  agent's CDP client and the user's own already-logged-in Chrome tab.
- No OpenRouter key. That travels frontend → Agent F → Agent B in-process;
  it never transits this relay.
- `CDP_WS_FRAME.data` is forwarded, not inspected, logged, or persisted.
- `url_host` fields are host-only — never a full URL with query
  strings/tokens.
- `session_token` is a single unguessable string (`secrets.token_urlsafe(32)`)
  scoping exactly one companion/one browser; there is no endpoint that lets
  one session enumerate or address another user's tunnel.
- `9222` is never exposed to the internet — only the companion's single
  outbound tunnel egresses the user's machine.

## What was NOT verified (be honest about this)

- **No real browser, no real Y6, no real companion process** were used —
  per the task boundary, this agent does not have Y6 access and was told not
  to deploy or run against the real Y6. `test_relay.py` plays the companion
  role itself over a real WebSocket to prove the relay's own logic; it does
  not prove a real Chrome + real `--remote-debugging-port=9222` + a real
  Agent C companion binary interoperate with this relay's wire format.
  Agent C (companion) and Agent B (browser-use) should smoke-test against a
  running `./run.sh` instance as part of Phase 2 integration.
- **SSE long-poll over a live open connection** (`GET /session/events`) is
  exercised structurally (the producer side — `_dispatch_companion_message`
  pushing onto `session.events` — runs in the happy-path test) but not read
  incrementally by a live streaming client in `test_relay.py`, because
  httpx's in-process ASGI test transport buffers a `StreamingResponse` until
  its generator returns, and this generator intentionally stays open for the
  session's lifetime. The `/session/gate/.../wait` long-poll endpoint (same
  underlying `asyncio.Event`) *is* exercised as a live bounded read. A real
  external HTTP client (e.g. Agent B's `httpx`/`aiohttp` SSE client) reading
  `/session/events` while a session is live has not been run in this task.
- **OQ-2 (browser-use's actual concurrent-CDP-target behavior)** is out of
  this agent's scope (Agent B's job per the spec's §1.4); the channel demux
  here supports arbitrarily many concurrent channels per companion, so it
  should absorb whatever browser-use does, but that has not been confirmed
  against a real browser-use run.
- **Heartbeat-miss force-close under a real half-open TCP connection**:
  `_heartbeat_watcher` force-closes the companion websocket once
  `HEARTBEAT_MISS_LIMIT_S` (2x `HEARTBEAT_INTERVAL_S`) passes with no
  `HEARTBEAT` message, reusing the one `WebSocketDisconnect` teardown path.
  This is covered by `test_heartbeat_miss_force_closes_companion` with a
  companion that registers and then goes silent — `websocket.close()` is a
  clean local call there, not a real network partition. A genuine half-open
  TCP connection (cable pulled, no FIN/RST) behaves differently at the
  socket layer than a same-process test closing its own end; that specific
  scenario has not been reproduced.
