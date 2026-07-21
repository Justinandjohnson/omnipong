# browser-use verification spike — closing OQ-1 through OQ-4

**Status:** Verification-only. No product code touched. Installed in a throwaway venv
(`/tmp/bu-spike`, Python 3.12) purely to read the installed source and confirm behavior
against `docs/RELAY_ARCHITECTURE.md` §0/§10.

**Pinned version:** `browser-use==0.13.6` (latest resolvable on PyPI at spike time,
2026-07-20; requires Python >=3.11 — installed under python3.12 since the default
python3 on this machine was 3.9).

Install command used:
```
python3.12 -m venv /tmp/bu-spike
/tmp/bu-spike/bin/pip install browser-use
# -> Successfully installed browser-use-0.13.6 (+ deps: cdp-use, browser-harness, browser-use-sdk, ...)
```

Source inspected at:
`/tmp/bu-spike/lib/python3.12/site-packages/browser_use/{__init__.py, browser/session.py, browser/session_manager.py, agent/service.py}`

---

## OQ-1 — Does browser-use accept a raw `ws://`/`wss://` `cdp_url`, or only HTTP?

**Answer: YES, it accepts a raw ws/wss URL, and this is a *different, simpler* code
path than the HTTP one — a real finding the relay design should account for.**

`browser/session.py`, `BrowserSession.connect()`:

```python
async def connect(self, cdp_url: str | None = None) -> Self:
    ...
    if not self.cdp_url.startswith('ws'):
        # If it's an HTTP URL, fetch the WebSocket URL from /json/version endpoint
        parsed_url = urlparse(self.cdp_url)
        path = parsed_url.path.rstrip('/')
        if not path.endswith('/json/version'):
            path = path + '/json/version'
        url = urlunparse((parsed_url.scheme, parsed_url.netloc, path, ...))
        async with httpx.AsyncClient(...) as client:
            version_info = await client.get(url, headers=headers)
            self.browser_profile.cdp_url = version_info.json()['webSocketDebuggerUrl']

    assert self.cdp_url is not None, 'CDP URL is None.'
    ...
    self._cdp_client_root = TimeoutWrappedCDPClient(
        self.cdp_url,
        additional_headers=headers or None,
        max_ws_frame_size=200 * 1024 * 1024,
    )
    await self._cdp_client_root.start()
```

The branch is a plain string check: `if not self.cdp_url.startswith('ws')`. If the
`cdp_url` you pass already starts with `ws` (`ws://` or `wss://`), browser-use **skips
the `/json/version` HTTP discovery step entirely** and hands that string straight to
`TimeoutWrappedCDPClient` as the browser-level devtools websocket. If it's an
`http(s)://` URL, it does exactly the two-step dance §1.1 of the architecture doc
describes (GET `/json/version`, read `webSocketDebuggerUrl`, connect to that).

**`Browser` vs `BrowserSession` alias — confirmed.** `browser_use/__init__.py`:
```python
_LAZY_IMPORTS = {
    ...
    'BrowserSession': ('browser_use.browser', 'BrowserSession'),
    'Browser': ('browser_use.browser', 'BrowserSession'),  # Alias for BrowserSession
    ...
}
```
`Browser` is literally the same class object as `BrowserSession`, re-exported under a
second name. No behavioral difference; use whichever name reads better.

**Impact on Agent A/B:** The doc's §1.4 explicitly says "design the HTTP-facade path
because it is what the docs prove works... don't design for raw-ws as a Phase-1
assumption." That caution was reasonable given the docs alone, but the installed
source shows raw `wss://` is not a hypothetical — it's a first-class, *simpler* branch
that skips HTTP-discovery proxying and header rewriting altogether. Recommend Agent A
still build the HTTP-facade proxy (§1.1) as the Phase-1 default since it's what
`scrape_existing_browser.py` already assumes and it's harder to get wrong at the
relay-rewrite layer — but flag the raw-`wss://` path as a legitimate Phase-2
simplification, not a maybe. Concretely: the relay could expose
`wss://relay…/cdp/{token}/devtools/browser/<id>` directly as `cdp_url` and skip
`/json/version` proxying+rewriting entirely, *if* the relay can mint/track that path
without discovery. Requires the relay to already know the browser target id
out-of-band (e.g. from the companion's registration payload), which it doesn't
currently — so Phase-1 should keep the HTTP-facade.

---

## OQ-2 — How many CDP websockets does browser-use open? (`get_or_create_cdp_session` sizing)

**Answer: Exactly ONE devtools websocket per `BrowserSession`, for the whole run,
regardless of how many tabs/targets the agent visits.** Multiple targets are
multiplexed over that single websocket using CDP's native "flatten" session mode
(`sessionId` embedded per-message), not by opening additional websockets.

Evidence, `browser/session.py`:
- `_cdp_client_root: CDPClient | None = PrivateAttr(default=None)` — one root client
  per `BrowserSession` instance, created once in `connect()`.
- `get_or_create_cdp_session(target_id, focus)` — despite the name, this does **not**
  open a new connection. It looks up an existing `CDPSession` from an in-memory pool
  (`self.session_manager._get_session_for_target(target_id)`), or waits up to 2s for
  Chrome to fire an `attachedToTarget` event that populates the pool.

`browser/session_manager.py`:
```python
await cdp_client.send.Target.attachToTarget(params={'targetId': target_id, 'flatten': True})
...
cdp_session = CDPSession(
    ...
    cdp_client=self.browser_session._cdp_client_root,   # <-- same root client, every target
    ...
)
```
`flatten: True` is the CDP mode where all target sessions ride one websocket
connection, distinguished by a `sessionId` field on each CDP message — this is exactly
why `cdp_client=self.browser_session._cdp_client_root` is reused for every
`CDPSession` rather than a fresh `CDPClient` being constructed per target.

**Impact on Agent A:** the relay's `channel` demux (§4.3) only ever needs to carry
**one** `CDP_WS_OPEN` per session — one devtools websocket for the browser's whole
lifetime, covering `Target.attachToTarget`/`detachFromTarget` traffic and all
per-tab CDP calls multiplexed inside it via `sessionId` in the JSON payload (which the
relay forwards opaquely per §5 anyway). The doc's assumption that `channel` needs to
size for "N devtools websockets" is more conservative than necessary for this
browser-use version — 1 channel suffices; keep the `channel` field for future-proofing
against a browser-use version that changes this, but Phase-1 traffic will only ever
use channel 1 plus the HTTP discovery channel.

---

## OQ-3 — pause()/resume() semantics

**(a) Does `pause()` stop the *next* step's actions, or can it also stop the step
currently in flight? Answer: it only gates the next loop iteration. If called from
inside `on_step_start`, the step that hook belongs to still runs its actions
unconditionally.**

`agent/service.py`, main loop:
```python
while self.state.n_steps <= max_steps:
    ...
    if self.state.paused:
        self.logger.debug(f'⏸️ Step {self.state.n_steps}: Agent paused, waiting to resume...')
        await self._external_pause_event.wait()
        signal_handler.reset()
    ...
    is_done = await self._execute_step(current_step, max_steps, step_info, on_step_start, on_step_end)
```
and `_execute_step`:
```python
async def _execute_step(self, step, max_steps, step_info, on_step_start=None, on_step_end=None) -> bool:
    if on_step_start is not None:
        await on_step_start(self)          # <- gate-detection + agent.pause() happens here
    ...
    await asyncio.wait_for(self.step(step_info), timeout=self.settings.step_timeout)  # <- runs unconditionally right after
    ...
    if on_step_end is not None:
        await on_step_end(self)
```
There is no pause check between `on_step_start` returning and `self.step()` firing.
So: calling `agent.pause()` inside `on_step_start` (as the architecture doc's §3.1
design does) does **not** stop the actions belonging to that same step —
`self.step(step_info)` runs regardless. The `if self.state.paused: await
self._external_pause_event.wait()` check only runs at the **top of the next loop
iteration**, i.e. it blocks step N+1 from starting, not step N's actions once
`on_step_start` for step N has already returned.

**Concrete implication:** if gate detection lives in `on_step_start` per §3.1, the step
that *triggers* pause (e.g., the step where the agent's LLM decides to click "Log in")
will still execute its planned action before the pause takes effect. If the LLM's
planned action for that step is itself the problematic action (e.g. submitting a form
into a Cloudflare challenge), it fires anyway. The doc's §3.4 fallback — "keep the hook
blocking on an `asyncio.Event`" — needs to be the *actual* Phase-1 design, not a
fallback: to truly stop the in-flight step, the `on_step_start` hook itself must
`await` the gate-cleared signal (block inside the hook) rather than calling
`pause()`+returning and trusting the next-iteration check. Calling `pause()` alongside
this is still useful as a defense-in-depth flag (prevents runaway if something calls
`agent.step()` directly elsewhere), but it is not sufficient alone.

**(b) Can `resume()` be called safely from an async callback (not just inside the hook
frame)? Answer: yes.**

```python
def pause(self) -> None:
    self.state.paused = True
    self._external_pause_event.clear()

def resume(self) -> None:
    self.state.paused = False
    self._external_pause_event.set()
```
Both are plain synchronous methods — no `await`, no coroutine, just a bool flag flip
and an `asyncio.Event.set()`/`.clear()`. `asyncio.Event` methods are safe to call from
any coroutine/callback running on the **same event loop**, regardless of call stack —
there is nothing tying `resume()` to the original hook's stack frame. The loop is
sitting at `await self._external_pause_event.wait()` (service.py line 2596) and will
simply wake up whenever `.set()` is called from anywhere in that event loop, including
a relay-listener task handling `GATE_CLEARED`. The only constraint (implicit from
asyncio itself, not stated in the source) is that it must be called from the **same
event loop** the agent is running in — a cross-thread relay listener would need
`loop.call_soon_threadsafe(agent.resume)` rather than a direct call. If the relay's
event listener and the browser-use agent share one asyncio event loop (the expected
Agent B architecture — one process, one loop), a plain `await`-free `agent.resume()`
call from the `GATE_CLEARED` handler is safe and requires no extra synchronization.

**Impact on Agent B:** implement the gate hook as blocking (`await` an
`asyncio.Event` set by the relay-signal handler) rather than fire-and-forget
`pause()`, to actually stop the triggering step's action, per (a). `resume()` can then
be called directly from the relay's async `GATE_CLEARED` handler with no extra
plumbing, per (b) — as long as both run on the same event loop, which they will in the
Agent B process.

---

## OQ-4 — Header naming (`X-User-Api-Key` vs `X-User-OpenRouter-Key`)

Not a source-verifiable question — this is a naming/routing decision for Agent E↔F,
not something browser-use's code can answer. Recommendation only, no code changed:

**Add a distinct `X-User-OpenRouter-Key` header rather than overloading
`X-User-Api-Key`.** Reasons:
- `X-User-Api-Key` today has an implicit meaning ("the Anthropic key for
  `ai_handler.py`") baked into `main.py: _get_user_ai_key`; silently repurposing it
  for a differently-shaped key (OpenRouter) for a different code path (browser-use's
  LLM client) creates an ambiguous contract the moment both are supplied at once,
  which the doc itself calls out as the exact failure case ("If a user supplies
  *both*...").
  - A single header can't disambiguate two simultaneously-present keys without an
    additional out-of-band signal (e.g., which endpoint was hit) — which reintroduces
    implicit coupling between transport (header) and routing (which tool needs which
    key), the thing the owner's "no fallback chains, one method per function" rule
    argues against.
- A second, explicitly-named header keeps the two credentials structurally separate at
  the one place (Agent F ingress) where both are visible, so routing to
  `ai_handler.py` vs. the browser-use LLM client is a straight 1:1 header→consumer
  mapping with no conditional logic and no fallback if one is missing/malformed.

This is a recommendation for Agent E/F to adopt when they touch that code — not
implemented here.

---

## Summary table

| OQ | Question | Answer | Evidence location |
|---|---|---|---|
| 1 | raw ws/wss `cdp_url` accepted? | **Yes** — `startswith('ws')` skips HTTP discovery entirely; `Browser` confirmed to be a plain alias of `BrowserSession` | `browser/session.py: connect()`; `browser_use/__init__.py: _LAZY_IMPORTS` |
| 2 | multiple devtools websockets per run? | **No** — one root `CDPClient` per session; all targets multiplexed over it via CDP `flatten` mode + `sessionId` | `browser/session.py: _cdp_client_root, get_or_create_cdp_session`; `browser/session_manager.py: attachToTarget(flatten=True)`, `CDPSession(cdp_client=...)` |
| 3a | does `pause()` stop the *current* step's actions? | **No** — only gates the *next* loop iteration; a step already past `on_step_start` runs its action unconditionally | `agent/service.py: _execute_step`, main loop pause check |
| 3b | is `resume()` safe from an async callback outside the hook frame? | **Yes**, same event loop only — plain sync method, no coroutine/stack coupling | `agent/service.py: pause()/resume()` |
| 4 | header naming | Not source-answerable — recommend a distinct `X-User-OpenRouter-Key` | N/A (judgment call, flagged for Agent E/F) |

## What was NOT verified (explicit)

- No live relay, companion, or real Chrome instance was exercised — this spike reads
  installed source only, per the task's throwaway/no-deploy scope. The `ws://` vs
  `http://` connect paths above were confirmed by reading `connect()`'s logic, not by
  running a live CDP round-trip against a real `wss://` endpoint.
- `TimeoutWrappedCDPClient` / `cdp-use`'s own internal framing (how it serializes CDP
  JSON over the websocket, timeout wrapping behavior) was not inspected beyond
  confirming it's constructed once per `BrowserSession` — irrelevant to OQ-1/2 as
  posed, but worth a follow-up read if Agent A needs exact wire-frame details.
- Did not test actual `pause()`/`resume()` behavior against a running agent+browser;
  this is a static-source read, consistent with "one method per function, verify
  before shipping" — Agent B should still smoke-test the blocking-hook pattern against
  a live run before merge, per the workspace's real-smoke-test rule.
