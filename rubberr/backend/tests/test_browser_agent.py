"""
Tests for rubberr/backend/browser_agent.py (Agent B).

These are unit tests, not a smoke test — per the repo's own rule, they prove
the gate pause/resume state machine and normalization logic behave as coded,
NOT that a real browser-use Agent / real OpenRouter / real relay works
end-to-end. No real browser, no real network call, no real LLM: the
browser-use `Agent` is a Mock, and the relay is a fake in-process
RelayGateClient double. That real-path verification is explicitly out of
scope here (needs Y6 + a real user login, per the task).

Run: python -m pytest rubberr/backend/tests/test_browser_agent.py -v
"""

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from browser_agent import (  # noqa: E402
    BrowserTaskResult,
    CdpLost,
    CompanionDisconnected,
    GateNotSolved,
    RelayGateClient,
    RelayUnreachable,
    build_gate_hook,
    classify_runtime_error,
    detect_gate,
    extract_raw_matches,
    extract_steps_used,
    normalize_matches,
    run_browser_task,
)


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class FakeGateClient:
    """Stands in for RelayGateClient. Records calls; lets a test script
    exactly what wait_for_clearance should return (True/False) or raise."""

    def __init__(self, clearance_result=True, clearance_exc=None):
        self.opened: list[tuple] = []
        self.waited: list[tuple] = []
        self._clearance_result = clearance_result
        self._clearance_exc = clearance_exc

    async def open_gate(self, gate_id, kind, hint, url_host):
        self.opened.append((gate_id, kind, hint, url_host))

    async def wait_for_clearance(self, gate_id, timeout_s):
        self.waited.append((gate_id, timeout_s))
        if self._clearance_exc is not None:
            raise self._clearance_exc
        return self._clearance_result

    async def aclose(self):
        pass


def make_fake_agent(url: str, page_text: str = ""):
    """A Mock standing in for browser_use.Agent, exposing exactly the
    surface the hook touches: browser_session.get_browser_state_summary(),
    .pause(), .resume()."""
    agent = MagicMock()
    agent.pause = MagicMock()
    agent.resume = MagicMock()
    state = SimpleNamespace(url=url, page_text=page_text)
    agent.browser_session.get_browser_state_summary = AsyncMock(return_value=state)
    return agent


# ---------------------------------------------------------------------------
# detect_gate — pure function
# ---------------------------------------------------------------------------


def test_detect_gate_login_path():
    kind, hint = detect_gate("https://stadiumcompete.com/log-in", "")
    assert kind == "login"
    assert "log in" in hint.lower()


def test_detect_gate_cloudflare_url():
    kind, _ = detect_gate("https://stadiumcompete.com/__cf_chl/abc", "")
    assert kind == "cloudflare"


def test_detect_gate_cloudflare_text():
    kind, _ = detect_gate("https://stadiumcompete.com/matches", "Checking your browser before...")
    assert kind == "cloudflare"


def test_detect_gate_captcha_text():
    kind, _ = detect_gate("https://stadiumcompete.com/verify", "Please complete the hCaptcha below")
    assert kind == "captcha"


def test_detect_gate_twofa_text():
    kind, _ = detect_gate("https://stadiumcompete.com/verify", "Enter your one-time code")
    assert kind == "twofa"


def test_detect_gate_none_on_normal_page():
    assert detect_gate("https://stadiumcompete.com/matches", "Your matches: 3-1 vs Grace Hopper") is None


# ---------------------------------------------------------------------------
# The gate pause/resume state machine (build_gate_hook), fully mocked
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_hook_noop_when_no_gate_detected():
    agent = make_fake_agent("https://stadiumcompete.com/matches", "some normal match text")
    gate_client = FakeGateClient()
    hook = build_gate_hook(gate_client, on_gate=None)

    await hook(agent)

    agent.pause.assert_not_called()
    agent.resume.assert_not_called()
    assert gate_client.opened == []


@pytest.mark.asyncio
async def test_hook_pauses_opens_gate_and_resumes_on_clearance():
    agent = make_fake_agent("https://stadiumcompete.com/log-in")
    gate_client = FakeGateClient(clearance_result=True)
    events = []

    async def on_gate(evt):
        events.append(evt)

    hook = build_gate_hook(gate_client, on_gate=on_gate, gate_ttl_s=5.0)

    await hook(agent)

    # State machine order: pause -> gate_open callback -> relay open_gate ->
    # wait_for_clearance -> gate_cleared callback -> resume.
    agent.pause.assert_called_once()
    agent.resume.assert_called_once()
    assert len(gate_client.opened) == 1
    gate_id, kind, hint, host = gate_client.opened[0]
    assert kind == "login"
    assert host == "stadiumcompete.com"
    assert gate_client.waited == [(gate_id, 5.0)]
    assert [e["event"] for e in events] == ["gate_open", "gate_cleared"]
    assert events[0]["gate_id"] == gate_id == events[1]["gate_id"]


@pytest.mark.asyncio
async def test_hook_raises_gate_not_solved_and_never_resumes_on_timeout():
    agent = make_fake_agent("https://stadiumcompete.com/log-in")
    gate_client = FakeGateClient(clearance_result=False)
    events = []

    async def on_gate(evt):
        events.append(evt)

    hook = build_gate_hook(gate_client, on_gate=on_gate, gate_ttl_s=1.0)

    with pytest.raises(GateNotSolved):
        await hook(agent)

    agent.pause.assert_called_once()
    agent.resume.assert_not_called()  # critical: never resumes an unsolved gate
    assert [e["event"] for e in events] == ["gate_open", "gate_timeout"]


@pytest.mark.asyncio
async def test_hook_propagates_relay_unreachable_without_resuming():
    agent = make_fake_agent("https://stadiumcompete.com/log-in")
    gate_client = FakeGateClient(clearance_exc=RelayUnreachable("connection refused"))

    hook = build_gate_hook(gate_client, on_gate=None)

    with pytest.raises(RelayUnreachable):
        await hook(agent)

    agent.pause.assert_called_once()
    agent.resume.assert_not_called()


@pytest.mark.asyncio
async def test_hook_assigns_sequential_gate_ids_across_multiple_gates():
    gate_client = FakeGateClient(clearance_result=True)
    hook = build_gate_hook(gate_client, on_gate=None, gate_ttl_s=5.0)

    agent1 = make_fake_agent("https://stadiumcompete.com/log-in")
    await hook(agent1)
    agent2 = make_fake_agent("https://stadiumcompete.com/log-in")
    await hook(agent2)

    gate_ids = [g[0] for g in gate_client.opened]
    assert gate_ids == ["g_01", "g_02"]


# ---------------------------------------------------------------------------
# classify_runtime_error
# ---------------------------------------------------------------------------


def test_classify_relay_unreachable():
    err = classify_runtime_error(Exception("Connection refused talking to relay"))
    assert err.status == "relay_unreachable"


def test_classify_cdp_lost():
    err = classify_runtime_error(Exception("Target closed: the CDP websocket errored"))
    assert err.status == "cdp_lost"


def test_classify_companion_gone():
    err = classify_runtime_error(Exception("SESSION_ENDED reason=companion_gone"))
    assert err.status == "companion_gone"


def test_classify_default_llm_error():
    err = classify_runtime_error(Exception("401 Unauthorized from OpenRouter"))
    assert err.status == "llm_error"


# ---------------------------------------------------------------------------
# normalize_matches / extract_raw_matches / extract_steps_used
# ---------------------------------------------------------------------------


def test_normalize_matches_happy_path():
    raw = [
        {
            "opponent": "Grace Hopper",
            "date": "May 11, 2026",
            "result": "W",
            "match_score": "3-1",
            "set_scores": ["11-8", "9-11", "11-6", "11-7"],
            "event": "Spring Open — U1800",
        }
    ]
    out = normalize_matches(raw, site="stadium", player_name="Ada Lovelace")
    assert out == [
        {
            "source": "stadium",
            "player_name": "Ada Lovelace",
            "opponent": "Grace Hopper",
            "date": "2026-05-11",
            "result": "W",
            "match_score": "3-1",
            "set_scores": ["11-8", "9-11", "11-6", "11-7"],
            "event": "Spring Open — U1800",
        }
    ]


def test_normalize_matches_drops_record_without_opponent():
    raw = [{"opponent": "", "date": "2026-05-11"}]
    assert normalize_matches(raw, site="stadium", player_name="X") == []


def test_normalize_matches_drops_record_with_invalid_source_for_usatt_site():
    raw = [{"opponent": "Someone", "source": "not_a_real_source"}]
    assert normalize_matches(raw, site="usatt", player_name="X") == []


def test_normalize_matches_no_player_name_hardcoding():
    """Regression guard for the spec's explicit rule: no hardcoded 'Justin'."""
    raw = [{"opponent": "Someone", "date": "2026-05-11", "result": "W"}]
    out = normalize_matches(raw, site="omnipong", player_name="Completely Different Person")
    assert out[0]["player_name"] == "Completely Different Person"
    assert "Justin" not in out[0]["player_name"]


def test_extract_raw_matches_parses_json_with_code_fence():
    history = MagicMock()
    history.final_result.return_value = '```json\n[{"opponent": "X"}]\n```'
    assert extract_raw_matches(history) == [{"opponent": "X"}]


def test_extract_raw_matches_empty_when_no_final_result():
    history = MagicMock()
    history.final_result.return_value = None
    assert extract_raw_matches(history) == []


def test_extract_raw_matches_raises_on_malformed_json():
    history = MagicMock()
    history.final_result.return_value = "not json at all"
    with pytest.raises(Exception):
        extract_raw_matches(history)


def test_extract_steps_used_uses_history_method():
    history = MagicMock()
    history.number_of_steps.return_value = 7
    assert extract_steps_used(history, max_steps=40) == 7


# ---------------------------------------------------------------------------
# run_browser_task input validation (no browser-use / network needed)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_browser_task_rejects_invalid_site():
    result = await run_browser_task(
        task="scrape",
        site="not-a-real-site",
        player_name="Ada",
        session_token="tok",
        openrouter_key="key",
        relay_base_url="https://relay.example.com",
    )
    assert isinstance(result, BrowserTaskResult)
    assert result.status == "llm_error"
    assert result.error["type"] == "InvalidSite"
    assert result.matches == []


@pytest.mark.asyncio
async def test_run_browser_task_rejects_missing_player_name():
    result = await run_browser_task(
        task="scrape",
        site="stadium",
        player_name="   ",
        session_token="tok",
        openrouter_key="key",
        relay_base_url="https://relay.example.com",
    )
    assert result.status == "llm_error"
    assert result.error["type"] == "InvalidPlayerName"


# ---------------------------------------------------------------------------
# run_browser_task end-to-end with a fully mocked browser_use module
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_browser_task_ok_path_with_mocked_browser_use(monkeypatch):
    """Exercises the full happy path — including a gate pause/resume inside
    agent.run() — with browser_use.Agent/Browser/ChatOpenAI all mocked, and
    the relay gate client faked. Proves run_browser_task wires the pieces
    together correctly; does NOT prove browser-use or OpenRouter actually
    work (that needs the real path, out of scope per the task)."""
    import browser_agent as ba

    fake_history = MagicMock()
    fake_history.final_result.return_value = (
        '[{"opponent": "Grace Hopper", "date": "2026-05-11", "result": "W", '
        '"match_score": "3-1", "set_scores": ["11-8", "11-6"], "event": "League"}]'
    )
    fake_history.number_of_steps.return_value = 12

    mock_agent_instance = MagicMock()

    async def fake_run(on_step_start=None, max_steps=40):
        # Simulate the real agent driving one step that hits a gate, so the
        # hook's full pause -> relay -> resume path actually executes.
        fake_browser_agent = make_fake_agent("https://stadiumcompete.com/log-in")
        await on_step_start(fake_browser_agent)
        fake_browser_agent.pause.assert_called_once()
        fake_browser_agent.resume.assert_called_once()
        return fake_history

    mock_agent_instance.run = fake_run

    mock_agent_cls = MagicMock(return_value=mock_agent_instance)
    mock_browser_cls = MagicMock()
    mock_chat_openai_cls = MagicMock()

    fake_module = SimpleNamespace(
        Agent=mock_agent_cls,
        Browser=mock_browser_cls,
        ChatOpenAI=mock_chat_openai_cls,
    )
    monkeypatch.setitem(sys.modules, "browser_use", fake_module)
    monkeypatch.setattr(ba, "RelayGateClient", lambda *a, **k: FakeGateClient(clearance_result=True))

    result = await run_browser_task(
        task="Scrape my Stadium singles match set-scores",
        site="stadium",
        player_name="Ada Lovelace",
        session_token="tok_abc",
        openrouter_key="or_key",
        relay_base_url="https://relay.example.com",
    )

    assert result.status == "ok"
    assert result.steps_used == 12
    assert result.error is None
    assert result.matches == [
        {
            "source": "stadium",
            "player_name": "Ada Lovelace",
            "opponent": "Grace Hopper",
            "date": "2026-05-11",
            "result": "W",
            "match_score": "3-1",
            "set_scores": ["11-8", "11-6"],
            "event": "League",
        }
    ]
    mock_browser_cls.assert_called_once_with(cdp_url="https://relay.example.com/cdp/tok_abc")
    mock_chat_openai_cls.assert_called_once_with(
        model="google/gemini-3-pro-preview",
        api_key="or_key",
        base_url="https://openrouter.ai/api/v1",
    )


@pytest.mark.asyncio
async def test_run_browser_task_gate_timeout_status(monkeypatch):
    """When the hook's gate is never cleared, agent.run() raises
    GateNotSolved and run_browser_task must surface status='gate_timeout'
    with zero matches — never resume, never return partial data."""
    import browser_agent as ba

    mock_agent_instance = MagicMock()

    async def fake_run(on_step_start=None, max_steps=40):
        fake_browser_agent = make_fake_agent("https://stadiumcompete.com/log-in")
        await on_step_start(fake_browser_agent)  # will raise GateNotSolved
        raise AssertionError("should not reach here")

    mock_agent_instance.run = fake_run
    fake_module = SimpleNamespace(
        Agent=MagicMock(return_value=mock_agent_instance),
        Browser=MagicMock(),
        ChatOpenAI=MagicMock(),
    )
    monkeypatch.setitem(sys.modules, "browser_use", fake_module)
    monkeypatch.setattr(ba, "RelayGateClient", lambda *a, **k: FakeGateClient(clearance_result=False))

    result = await run_browser_task(
        task="scrape",
        site="stadium",
        player_name="Ada",
        session_token="tok",
        openrouter_key="key",
        relay_base_url="https://relay.example.com",
    )

    assert result.status == "gate_timeout"
    assert result.matches == []
    assert result.error["type"] == "GateNotSolved"


@pytest.mark.asyncio
async def test_run_browser_task_cdp_lost_status(monkeypatch):
    mock_agent_instance = MagicMock()

    async def fake_run(on_step_start=None, max_steps=40):
        raise RuntimeError("Target closed: CDP websocket errored")

    mock_agent_instance.run = fake_run
    fake_module = SimpleNamespace(
        Agent=MagicMock(return_value=mock_agent_instance),
        Browser=MagicMock(),
        ChatOpenAI=MagicMock(),
    )
    import sys as _sys

    monkeypatch.setitem(_sys.modules, "browser_use", fake_module)

    result = await run_browser_task(
        task="scrape",
        site="stadium",
        player_name="Ada",
        session_token="tok",
        openrouter_key="key",
        relay_base_url="https://relay.example.com",
    )

    assert result.status == "cdp_lost"
    assert result.matches == []


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
