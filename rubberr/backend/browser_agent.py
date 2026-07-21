"""
Agent B — Browser-agent core (Rubberr Agent Platform, Phase 1).

Wraps `browser-use` to drive a remote user's own, already-logged-in Chrome
through the Rubberr relay (docs/RELAY_ARCHITECTURE.md), with a
human-in-the-loop pause/resume handshake at login / Cloudflare / 2FA /
captcha gates (§3), Gemini-via-OpenRouter as the brain (§6), and a frozen
`run_browser_task()` / `BrowserTaskResult` interface (§8) that Agent F calls.

Ownership: this file (+ tests/test_browser_agent.py) is owned exclusively by
Agent B. Do not import from main.py / ai_handler.py. This module never
touches the DB — it returns normalized matches[]; Agent F persists them.

Rule (owner's house rule, restated in the spec): one method per function, or
a clean typed error. No retries, no fallback chains, no silent degrade.

Verified against docs/BROWSER_USE_SPIKE.md (installed browser-use==0.13.6
source, read 2026-07-20) — the OQ-3 finding that matters most here:
`agent.pause()` alone does NOT stop the step that is already past
`on_step_start` (browser-use's main loop only checks the pause flag at the
*next* iteration; `self.step()` for the current step fires unconditionally
right after `on_step_start` returns). This module does not rely on
`pause()` alone: `build_gate_hook()` below blocks *inside* `on_step_start`
(awaiting the relay's GATE_CLEARED/GATE_TIMEOUT) before returning, which is
what actually prevents that step's action from firing — `pause()` is kept
only as a defense-in-depth flag, per the spike's recommendation.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Awaitable, Callable, Optional, TypedDict

import httpx

logger = logging.getLogger("rubberr.browser_agent")

# ---------------------------------------------------------------------------
# Frozen types — RELAY_ARCHITECTURE.md §8.1/§8.2/§8.3. Do not change shape
# without updating the spec and Agent F in lockstep.
# ---------------------------------------------------------------------------

VALID_SITES = {"stadium", "usatt", "omnipong"}
VALID_SOURCES = {"omnipong", "stadium", "stadium_league"}

# Which `source` a scrape of a given `site` produces when the agent doesn't
# tag its own record (§8.2's normalized shape reuses these three values).
# "usatt" has no direct entry in VALID_SOURCES (Tier-1 lookup, not a private
# match sync) — records for that site must carry their own valid `source`,
# or they are dropped rather than guessed (see _normalize_matches).
_SITE_TO_SOURCE = {"stadium": "stadium", "omnipong": "omnipong"}


@dataclass
class BrowserTaskResult:
    status: str  # "ok" | "gate_timeout" | "companion_gone"
    #              | "cdp_lost" | "llm_error" | "relay_unreachable"
    matches: list[dict]
    steps_used: int
    error: Optional[dict] = None


class GateEvent(TypedDict):
    event: str  # "gate_open" | "gate_cleared" | "gate_timeout"
    gate_id: str
    kind: str  # login | cloudflare | captcha | twofa | unknown
    hint: str
    url_host: str


GateCallback = Callable[[GateEvent], Awaitable[None]]

# ---------------------------------------------------------------------------
# Config defaults (spec §2.2 / §3.3)
# ---------------------------------------------------------------------------

# C4: same knob relay/config.py reads as RELAY_GATE_TTL_S — one source of
# truth for the gate hard-cap, read here under the shared env var name.
GATE_TTL_S = float(os.environ.get("RELAY_GATE_TTL_S", "300"))  # 5 min hard cap on an unsolved gate

# S3: same operator gate relay/config.py enforces on /session/gate — read
# here under the shared env var name so this owner-only control call
# presents it too. If unset, the relay's own fail-closed check (503) is what
# surfaces the misconfiguration; this client does not duplicate that check.
RELAY_OPERATOR_TOKEN = os.environ.get("RELAY_OPERATOR_TOKEN")

# ---------------------------------------------------------------------------
# Typed errors (F2/F3/F4/F6, §7). Exactly one of these maps to each non-"ok"
# BrowserTaskResult.status. No retries are attempted anywhere below.
# ---------------------------------------------------------------------------


class BrowserAgentError(Exception):
    status = "llm_error"
    steps_used: int = 0  # C5: real value set by callers that know it (see _agent_steps)

    def __init__(self, detail: str):
        super().__init__(detail)
        self.detail = detail


class GateNotSolved(BrowserAgentError):
    """F2 — gate opened but never cleared within GATE_TTL_S."""

    status = "gate_timeout"


class CompanionDisconnected(BrowserAgentError):
    """F1 — the user's companion tunnel dropped mid-scrape."""

    status = "companion_gone"


class CdpLost(BrowserAgentError):
    """F3 — the CDP connection to the user's browser died mid-run."""

    status = "cdp_lost"


class LlmError(BrowserAgentError):
    """F4 — OpenRouter/Gemini call failed (bad key, rate limit, 5xx, etc.)."""

    status = "llm_error"


class RelayUnreachable(BrowserAgentError):
    """F6 — could not reach relay_base_url at all."""

    status = "relay_unreachable"


# ---------------------------------------------------------------------------
# Gate detection (§3.1) — pure function, no I/O, independently testable.
# ---------------------------------------------------------------------------

_CLOUDFLARE_URL_HINTS = ("challenges.cloudflare.com", "__cf_chl")
_HUMAN_CHECK_TEXT_HINTS = ("verify you are human", "checking your browser", "cf-turnstile")
_CAPTCHA_TEXT_HINTS = ("hcaptcha", "recaptcha", "g-recaptcha", "turnstile")
_TWOFA_TEXT_HINTS = (
    "verification code",
    "enter code",
    "one-time code",
    "one time code",
    "two-factor",
    "two factor",
    " otp ",
)
_LOGIN_PATH_HINTS = ("log-in", "login", "sign-in", "signin", "/auth")


def _url_host(url: str) -> str:
    m = re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://([^/]+)", url or "")
    return m.group(1) if m else (url or "")


def detect_gate(url: str, page_text: str = "") -> Optional[tuple[str, str]]:
    """Returns (kind, hint) if the current page looks like a login /
    Cloudflare / captcha / 2FA gate, else None. `kind` is one of
    login | cloudflare | captcha | twofa (matches §4.4's enum, minus
    "unknown" which callers may use for signals not covered here)."""
    low_url = (url or "").lower()
    low_text = (page_text or "").lower()

    if any(h in low_url for h in _CLOUDFLARE_URL_HINTS) or any(
        h in low_text for h in _HUMAN_CHECK_TEXT_HINTS
    ):
        return "cloudflare", "Solve the Cloudflare check in your browser, then click Continue."
    if any(h in low_text for h in _CAPTCHA_TEXT_HINTS):
        return "captcha", "Solve the captcha in your browser, then click Continue."
    if any(h in low_text for h in _TWOFA_TEXT_HINTS):
        return "twofa", "Enter your verification code in your browser, then click Continue."
    if any(h in low_url for h in _LOGIN_PATH_HINTS):
        return "login", "Log in to your account in your browser, then click Continue."
    return None


def _extract_page_text(state: Any) -> str:
    """Best-effort cheap text signal from browser-use's BrowserStateSummary.
    The docs confirm `state.url`; a full-text field isn't documented, so this
    probes the couple of attribute names browser-use has used for page
    content across versions. This is attribute discovery, not a retry
    fallback — every branch is a plain getattr, no I/O, no alternate control
    path. Verify the exact attribute at pin time (flagged for Agent B)."""
    for attr in ("page_text", "text_content", "content"):
        val = getattr(state, attr, None)
        if isinstance(val, str) and val:
            return val
    dom_state = getattr(state, "dom_state", None) or getattr(state, "element_tree", None)
    if dom_state is not None:
        return str(dom_state)
    return ""


# ---------------------------------------------------------------------------
# Relay gate client (§3 message flow, §4.4 schema)
# ---------------------------------------------------------------------------


class RelayGateClient:
    """Owns exactly the two relay calls needed for the gate handshake:
    POST /session/gate to open a gate, and a blocking read of
    GET /session/events (SSE) filtered to one gate_id, until GATE_CLEARED,
    GATE_TIMEOUT, or the local deadline. No retries: any transport error
    raises RelayUnreachable immediately."""

    def __init__(
        self,
        relay_base_url: str,
        session_token: str,
        http_client: Optional[httpx.AsyncClient] = None,
    ):
        self._base = relay_base_url.rstrip("/")
        self._session_token = session_token
        self._client = http_client
        self._owns_client = http_client is None

    def _client_or_create(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=10.0)
        return self._client

    async def open_gate(self, gate_id: str, kind: str, hint: str, url_host: str) -> None:
        client = self._client_or_create()
        try:
            resp = await client.post(
                f"{self._base}/session/gate",
                json={
                    "type": "GATE_OPEN",
                    "session_token": self._session_token,
                    "gate_id": gate_id,
                    "kind": kind,
                    "hint": hint,
                    "url_host": url_host,
                },
                headers={"X-Operator-Token": RELAY_OPERATOR_TOKEN} if RELAY_OPERATOR_TOKEN else {},
            )
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise RelayUnreachable(f"relay unreachable opening gate {gate_id}: {exc}") from exc

    async def wait_for_clearance(self, gate_id: str, timeout_s: float) -> bool:
        """Blocks (via await, inside the caller's own on_step_start coroutine
        frame) until GATE_CLEARED for gate_id arrives over the relay's SSE
        event stream, GATE_TIMEOUT arrives, or timeout_s elapses locally as a
        backstop. Returns True iff cleared. This blocking-in-hook design is
        required, not optional: BROWSER_USE_SPIKE.md confirmed `pause()`
        alone does not stop the step already in flight when on_step_start is
        called, so the hook must not return until the gate is resolved."""
        client = self._client_or_create()
        deadline = time.monotonic() + timeout_s
        try:
            # Phase 2 fix: the relay exposes this SSE stream with the
            # session_token folded into the path — GET /session/events/{token}
            # (relay/server.py, matching relay/test_relay.py) — not a
            # ?session_token= query param. This was interface drift between
            # Agent A (relay) and Agent B (this client) from Phase 1; the
            # relay side is treated as authoritative since it's covered by
            # relay/test_relay.py.
            async with client.stream(
                "GET",
                f"{self._base}/session/events/{self._session_token}",
                timeout=httpx.Timeout(timeout_s + 5.0, connect=10.0),
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if time.monotonic() > deadline:
                        return False
                    if not line.startswith("data:"):
                        continue
                    try:
                        event = json.loads(line[len("data:") :].strip())
                    except ValueError:
                        continue
                    if event.get("gate_id") != gate_id:
                        continue
                    if event.get("type") == "GATE_CLEARED":
                        return True
                    if event.get("type") == "GATE_TIMEOUT":
                        return False
        except httpx.HTTPError as exc:
            raise RelayUnreachable(f"relay unreachable waiting on gate {gate_id}: {exc}") from exc
        return False

    async def aclose(self) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()


# ---------------------------------------------------------------------------
# on_step_start hook builder (§3.1/§3.2/§3.4). Signature confirmed against
# browser-use docs: `async def hook(agent): ...`, called with the live Agent.
# ---------------------------------------------------------------------------


def _agent_steps(agent: Any) -> int:
    """C5: browser-use's Agent tracks progress at `agent.state.n_steps`
    (confirmed in docs/BROWSER_USE_SPIKE.md's excerpt of the main loop).
    Real count when available, 0 if the attribute is genuinely absent —
    never a guess."""
    return int(getattr(getattr(agent, "state", None), "n_steps", 0) or 0)


def build_gate_hook(
    gate_client: RelayGateClient,
    on_gate: Optional[GateCallback],
    gate_ttl_s: float = GATE_TTL_S,
) -> Callable[[Any], Awaitable[None]]:
    """Builds the on_step_start hook passed to agent.run(). On each step it
    inspects browser state for a gate signature; if found it pauses the
    agent, opens the gate on the relay, blocks until cleared or timed out,
    then resumes (or raises GateNotSolved on timeout — never resumes without
    a clear)."""
    seen: list[str] = []

    async def on_step_start(agent: Any) -> None:
        state = await agent.browser_session.get_browser_state_summary()
        url = getattr(state, "url", "") or ""
        page_text = _extract_page_text(state)

        detected = detect_gate(url, page_text)
        if detected is None:
            return

        kind, hint = detected
        host = _url_host(url)
        gate_id = f"g_{len(seen) + 1:02d}"
        seen.append(gate_id)

        agent.pause()

        if on_gate is not None:
            await on_gate(
                {"event": "gate_open", "gate_id": gate_id, "kind": kind, "hint": hint, "url_host": host}
            )

        try:
            await gate_client.open_gate(gate_id, kind, hint, host)
            cleared = await gate_client.wait_for_clearance(gate_id, gate_ttl_s)
        except BrowserAgentError as exc:
            exc.steps_used = _agent_steps(agent)
            raise

        if not cleared:
            if on_gate is not None:
                await on_gate(
                    {
                        "event": "gate_timeout",
                        "gate_id": gate_id,
                        "kind": kind,
                        "hint": hint,
                        "url_host": host,
                    }
                )
            gate_not_solved = GateNotSolved(
                f"gate {gate_id} ({kind}) at {host} not solved within {gate_ttl_s:.0f}s"
            )
            gate_not_solved.steps_used = _agent_steps(agent)
            raise gate_not_solved

        if on_gate is not None:
            await on_gate(
                {"event": "gate_cleared", "gate_id": gate_id, "kind": kind, "hint": hint, "url_host": host}
            )
        agent.resume()

    return on_step_start


# ---------------------------------------------------------------------------
# Error classification for browser-use / OpenRouter runtime failures. Not a
# retry fallback: every branch still ends in exactly one clean typed error.
# browser-use does not (per the docs pulled for this build) expose distinct
# exception classes for CDP-loss vs LLM-failure, so this triages by message
# content. Flagged for Agent B to replace with isinstance checks once real
# exception types are confirmed against the pinned version.
# ---------------------------------------------------------------------------

_RELAY_UNREACHABLE_HINTS = ("connection refused", "name or service not known", "cannot connect to host")
_COMPANION_GONE_HINTS = ("companion_gone", "companion disconnected", "session_ended")
_CDP_LOST_HINTS = ("cdp", "websocket", "playwright", "target closed", "browser has been closed")


def classify_runtime_error(exc: Exception) -> BrowserAgentError:
    msg = str(exc).lower()
    if any(h in msg for h in _RELAY_UNREACHABLE_HINTS):
        return RelayUnreachable(str(exc))
    if any(h in msg for h in _COMPANION_GONE_HINTS):
        return CompanionDisconnected(str(exc))
    if any(h in msg for h in _CDP_LOST_HINTS):
        return CdpLost(str(exc))
    return LlmError(str(exc))


# ---------------------------------------------------------------------------
# Task prompt + result normalization (§8.2). Reuses the field vocabulary of
# stadium_league_scraper.py's parsed records without reusing its Playwright
# DOM code — browser-use's own LLM-driven extraction produces the raw
# records here; this only validates/coerces them into the frozen shape.
# ---------------------------------------------------------------------------


def build_task_prompt(task: str, site: str, player_name: str) -> str:
    return (
        f"{task}\n\n"
        f"You are already logged in as {player_name} on {site}. Do not attempt to log in "
        "yourself or enter any credentials — if you hit a login page, a Cloudflare check, "
        "a captcha, or a 2FA prompt, stop and wait; a human will solve it in this same "
        "browser tab.\n\n"
        "When you have gathered the match data, finish with `done` and put ONLY a JSON "
        "array of match records as the final result text — no prose, no markdown fences. "
        'Each record must use exactly these keys: "source" (one of "omnipong", "stadium", '
        '"stadium_league"), "player_name", "opponent", "date" (YYYY-MM-DD if you can '
        'determine it, else the raw date text), "result" ("W" or "L"), "match_score" '
        '(e.g. "3-1"), "set_scores" (a list of strings like "11-8"), "event" (tournament or '
        "league name). Use null for anything you didn't actually see on the page — never "
        "invent data."
    )


def _normalize_date(raw: Optional[str]) -> Optional[str]:
    if not raw:
        return None
    raw = raw.strip()
    for fmt in ("%Y-%m-%d", "%B %d, %Y"):
        try:
            return datetime.strptime(raw, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return raw


def normalize_matches(raw_matches: list[dict], *, site: str, player_name: str) -> list[dict]:
    expected_source = _SITE_TO_SOURCE.get(site)
    normalized: list[dict] = []

    for raw in raw_matches:
        if not isinstance(raw, dict):
            continue
        source = raw.get("source") or expected_source
        if source not in VALID_SOURCES:
            logger.warning("dropping match record with invalid source %r for site=%r", source, site)
            continue
        opponent = raw.get("opponent")
        if not opponent:
            logger.warning("dropping match record with no opponent: %r", raw)
            continue

        set_scores = raw.get("set_scores") or []
        if not isinstance(set_scores, list):
            set_scores = [str(set_scores)]

        normalized.append(
            {
                "source": source,
                "player_name": player_name,
                "opponent": opponent,
                "date": _normalize_date(raw.get("date")),
                "result": raw.get("result"),
                "match_score": raw.get("match_score"),
                "set_scores": [str(s) for s in set_scores],
                "event": raw.get("event") or "",
            }
        )

    return normalized


def extract_raw_matches(history: Any) -> list[dict]:
    """Pulls the agent's final JSON result (per build_task_prompt's
    contract) off an AgentHistoryList and parses it. history.final_result()
    is a documented browser-use method returning the last extracted content
    as a string."""
    final_result = history.final_result()
    if not final_result:
        return []

    if isinstance(final_result, (list, dict)):
        parsed: Any = final_result
    elif isinstance(final_result, str):
        text = final_result.strip()
        text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.MULTILINE).strip()
        parsed = json.loads(text)
    else:
        raise ValueError(f"unrecognized final_result type: {type(final_result)!r}")

    if isinstance(parsed, dict):
        parsed = [parsed]
    if not isinstance(parsed, list):
        raise ValueError("final_result JSON is not a list of match records")

    return [p for p in parsed if isinstance(p, dict)]


# ---------------------------------------------------------------------------
# Tier-1 USATT profile lookup (site == "usatt") — Phase 2 addition.
#
# build_task_prompt()/normalize_matches()/extract_raw_matches() above are
# frozen to the match-array shape (§8.2) and covered by
# tests/test_browser_agent.py's direct calls with site="usatt" (which assert
# normalize_matches still filters unknown-source records) — this section does
# NOT change any of that. USATT rating lookup is not a match sync; it needs a
# single player-profile object (name/rating/history/tournaments), which the
# match-array contract has no field for. run_browser_task branches to this
# separate prompt/extractor pair for site == "usatt" instead of routing
# through normalize_matches, so both contracts stay intact and independently
# testable.
# ---------------------------------------------------------------------------


def build_usatt_task_prompt(player_name: str) -> str:
    return (
        f"Search USATT (usatt.simplycompete.com) for the player '{player_name}' and "
        "extract their current rating, USATT ID, state, rating history, and recent "
        "tournament results. Do not attempt to log in — this is a public lookup.\n\n"
        "When done, finish with `done` and put ONLY a single JSON object as the final "
        "result text — no prose, no markdown fences — with exactly these keys:\n"
        '  "not_found": true if no matching player was found, else false,\n'
        '  "player": {"name": ..., "usatt_id": ..., "rating": ..., "state": ...} or null,\n'
        '  "rating_history": [{"date": "YYYY-MM-DD", "rating": ...}, ...] (possibly empty),\n'
        '  "tournaments": [{"title": ..., "date_range": ..., "location": ..., "result": ...}, ...] '
        "(possibly empty).\n"
        "Use null for anything you didn't actually see on the page — never invent data."
    )


def extract_usatt_profile(history: Any) -> dict:
    """Pulls and validates the single USATT profile JSON object off an
    AgentHistoryList, per build_usatt_task_prompt's contract. Mirrors
    extract_raw_matches' parsing (code-fence stripping, JSON decode) but
    expects one object, not an array of match records."""
    final_result = history.final_result()
    if not final_result:
        return {"not_found": True, "player": None, "rating_history": [], "tournaments": []}

    if isinstance(final_result, dict):
        parsed: Any = final_result
    elif isinstance(final_result, str):
        text = final_result.strip()
        text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.MULTILINE).strip()
        parsed = json.loads(text)
    else:
        raise ValueError(f"unrecognized final_result type: {type(final_result)!r}")

    if not isinstance(parsed, dict):
        raise ValueError("USATT final_result JSON is not a single object")

    player = parsed.get("player")
    return {
        "not_found": bool(parsed.get("not_found")) or player is None,
        "player": player if isinstance(player, dict) else None,
        "rating_history": parsed.get("rating_history") if isinstance(parsed.get("rating_history"), list) else [],
        "tournaments": parsed.get("tournaments") if isinstance(parsed.get("tournaments"), list) else [],
    }


# ---------------------------------------------------------------------------
# Input validation (S2) — player_name and task are interpolated raw into the
# LLM prompt by build_task_prompt/build_usatt_task_prompt; validate them here
# (the run_browser_task boundary) AND again at the backend request boundary
# in main.py, which imports these same two functions rather than
# reimplementing the rules a second time.
# ---------------------------------------------------------------------------

_CONTROL_CHAR_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_PLAYER_NAME_RE = re.compile(r"^[A-Za-z0-9 .,'\-]{1,100}$")
MAX_TASK_LEN = 2000


def validate_player_name(player_name: str) -> Optional[str]:
    """Returns an error string if player_name is invalid, else None. Sane
    name charset only (letters, digits, spaces, . , ' -), 1-100 chars —
    rejects newlines/control characters as a side effect of the allowlist."""
    if not player_name or not player_name.strip():
        return "player_name is required"
    if not _PLAYER_NAME_RE.match(player_name):
        return "player_name must be 1-100 characters of letters, digits, spaces, and . , ' -"
    return None


def validate_task_text(task: str) -> Optional[str]:
    """Returns an error string if task is invalid, else None. Free-text
    prose, so no charset allowlist — just a length cap and no control
    characters/newlines."""
    if len(task) > MAX_TASK_LEN:
        return f"task must be {MAX_TASK_LEN} characters or fewer"
    if _CONTROL_CHAR_RE.search(task):
        return "task must not contain control characters"
    return None


def extract_steps_used(history: Any, max_steps: int) -> int:
    """history.number_of_steps() is a documented browser-use method. Falls
    back to max_steps only if the object genuinely lacks it (e.g. a mock in
    tests), never as an error-recovery retry."""
    if hasattr(history, "number_of_steps"):
        return int(history.number_of_steps())
    return max_steps


# ---------------------------------------------------------------------------
# Frozen entry point — RELAY_ARCHITECTURE.md §8.1
# ---------------------------------------------------------------------------


async def run_browser_task(
    *,
    task: str,
    site: str,
    player_name: str,
    session_token: str,
    openrouter_key: str,
    model: str = "google/gemini-3-pro-preview",
    relay_base_url: str,
    on_gate: Optional[GateCallback] = None,
    max_steps: int = 40,
) -> BrowserTaskResult:
    if site not in VALID_SITES:
        return BrowserTaskResult(
            status="llm_error",
            matches=[],
            steps_used=0,
            error={"type": "InvalidSite", "detail": f"site must be one of {sorted(VALID_SITES)}, got {site!r}"},
        )
    name_error = validate_player_name(player_name)
    if name_error:
        return BrowserTaskResult(
            status="llm_error",
            matches=[],
            steps_used=0,
            error={"type": "InvalidPlayerName", "detail": name_error},
        )
    task_error = validate_task_text(task)
    if task_error:
        return BrowserTaskResult(
            status="llm_error",
            matches=[],
            steps_used=0,
            error={"type": "InvalidTask", "detail": task_error},
        )

    try:
        from browser_use import Agent, Browser, ChatOpenAI
    except ImportError as exc:
        return BrowserTaskResult(
            status="llm_error",
            matches=[],
            steps_used=0,
            error={"type": "DependencyMissing", "detail": f"browser-use not installed: {exc}"},
        )

    cdp_url = f"{relay_base_url.rstrip('/')}/cdp/{session_token}"
    gate_client = RelayGateClient(relay_base_url, session_token)
    steps_used = 0

    try:
        llm = ChatOpenAI(model=model, api_key=openrouter_key, base_url="https://openrouter.ai/api/v1")
        browser = Browser(cdp_url=cdp_url)
        hook = build_gate_hook(gate_client, on_gate)

        agent = Agent(
            task=build_usatt_task_prompt(player_name) if site == "usatt" else build_task_prompt(task, site, player_name),
            llm=llm,
            browser=browser,
            # E1: these are pure DOM/text extraction tasks and detect_gate()
            # never looks at pixels — no reason to ship a screenshot every
            # step to Gemini Pro.
            use_vision=False,
        )

        try:
            history = await agent.run(on_step_start=hook, max_steps=max_steps)
        except BrowserAgentError as exc:
            steps_used = getattr(exc, "steps_used", 0)
            return BrowserTaskResult(
                status=exc.status,
                matches=[],
                steps_used=steps_used,
                error={"type": type(exc).__name__, "detail": exc.detail},
            )
        except Exception as exc:
            typed = classify_runtime_error(exc)
            return BrowserTaskResult(
                status=typed.status,
                matches=[],
                steps_used=_agent_steps(agent),
                error={"type": type(typed).__name__, "detail": typed.detail},
            )

        steps_used = extract_steps_used(history, max_steps)

        if site == "usatt":
            try:
                profile = extract_usatt_profile(history)
            except Exception as exc:
                return BrowserTaskResult(
                    status="llm_error",
                    matches=[],
                    steps_used=steps_used,
                    error={"type": "UsattProfileExtractionFailed", "detail": str(exc)},
                )
            # BrowserTaskResult.matches is frozen as list[dict] (§8.2); for the
            # usatt site that list carries exactly one element — the profile
            # object — rather than match records. Agent F unpacks matches[0].
            return BrowserTaskResult(status="ok", matches=[profile], steps_used=steps_used, error=None)

        try:
            raw_matches = extract_raw_matches(history)
        except Exception as exc:
            return BrowserTaskResult(
                status="llm_error",
                matches=[],
                steps_used=steps_used,
                error={"type": "MatchExtractionFailed", "detail": str(exc)},
            )

        matches = normalize_matches(raw_matches, site=site, player_name=player_name)
        return BrowserTaskResult(status="ok", matches=matches, steps_used=steps_used, error=None)

    finally:
        await gate_client.aclose()
