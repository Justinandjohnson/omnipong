"""
Phase 2 integration test — the F -> SSE -> frontend-contract path.

Proves the seam wired in main.py (`_start_tier3_sync` / `_run_and_stream_browser_task`
/ `_sse_response_for_sync_session`) actually bridges Agent B's `on_gate` callback
into the exact SSE event stream `StadiumSyncPanel.tsx` (Agent E) expects:
POST /tools/sync/stadium -> {"session_id": ...}, then
GET /tools/sync/stadium/events/{session_id} emitting named SSE events
gate_open / gate_cleared / done, with the "done" payload matching
BrowserTaskResult's frozen shape (RELAY_ARCHITECTURE.md §8.2).

No real browser, relay, or Chrome: relay/session/start and
browser_agent.run_browser_task are both faked in-process, exactly like
tests/test_browser_agent.py fakes RelayGateClient. What this proves:
the SSE bridge wiring in main.py is correct. What it does NOT prove: that a
real relay/browser-use run behaves this way end to end (Phase 4, needs Y6 +
a real browser).

Run: python -m pytest rubberr/backend/tests/test_sync_sse_integration.py -v
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_DIR.parent.parent

# --- Stub heavyweight optional deps main.py imports transitively, exactly
# like test_browser_agent.py stubs `browser_use` — this is dependency
# discovery/isolation for the test environment, not a product fallback path.
sys.modules.setdefault("playwright", MagicMock())
sys.modules.setdefault("playwright.async_api", SimpleNamespace(async_playwright=MagicMock()))
sys.modules.setdefault("openai", SimpleNamespace(OpenAI=MagicMock()))

sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(BACKEND_DIR))

from fastapi.testclient import TestClient  # noqa: E402

from rubberr.backend import main as backend_main  # noqa: E402
from rubberr.backend.browser_agent import BrowserTaskResult  # noqa: E402


def _parse_sse(body: str) -> list[tuple[str, dict]]:
    """Splits a raw SSE response body into (event, data) pairs, mirroring
    what a browser EventSource / StadiumSyncPanel.tsx's addEventListener
    actually consumes."""
    events = []
    for block in body.strip().split("\n\n"):
        if not block.strip():
            continue
        event_name = None
        data_line = None
        for line in block.splitlines():
            if line.startswith("event:"):
                event_name = line[len("event:") :].strip()
            elif line.startswith("data:"):
                data_line = line[len("data:") :].strip()
        assert event_name is not None and data_line is not None
        import json

        events.append((event_name, json.loads(data_line)))
    return events


@pytest.fixture(autouse=True)
def _clean_queue_state():
    backend_main._sync_event_queues.clear()
    yield
    backend_main._sync_event_queues.clear()


def test_stadium_sync_start_and_sse_bridge(monkeypatch):
    monkeypatch.setenv("RELAY_BASE_URL", "https://relay.example.com")
    monkeypatch.setenv("RELAY_REGISTER_TOKEN", "rt_test_owner")
    monkeypatch.setenv("OPERATOR_TOKEN", "op_test_token")

    # Fake relay session provisioning (no real relay) — mints a fixed token.
    async def fake_provision(register_token, *, relay_base_url):
        assert register_token == "rt_test_owner"
        assert relay_base_url == "https://relay.example.com"
        return "st_fake_session_123"

    monkeypatch.setattr(backend_main, "_provision_relay_session", fake_provision)

    # Fake Agent B: emits one gate_open/gate_cleared round trip via on_gate,
    # then returns the frozen BrowserTaskResult shape (§8.2).
    async def fake_run_browser_task(*, task, site, player_name, session_token, openrouter_key, model, relay_base_url, on_gate=None, max_steps=40):
        assert site == "stadium"
        assert player_name == "Ada Lovelace"
        assert session_token == "st_fake_session_123"
        assert openrouter_key == "or_test_key"
        await on_gate({"event": "gate_open", "gate_id": "g_01", "kind": "login", "hint": "Log in, then continue.", "url_host": "stadiumcompete.com"})
        await on_gate({"event": "gate_cleared", "gate_id": "g_01", "kind": "login", "hint": "Log in, then continue.", "url_host": "stadiumcompete.com"})
        return BrowserTaskResult(
            status="ok",
            matches=[
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
            ],
            steps_used=5,
            error=None,
        )

    monkeypatch.setattr(backend_main, "run_browser_task", fake_run_browser_task)
    monkeypatch.setattr(backend_main, "BROWSER_AGENT_AVAILABLE", True)

    with TestClient(backend_main.app) as client:
        start_resp = client.post(
            "/tools/sync/stadium",
            headers={"X-User-Api-Key": "or_test_key", "X-Operator-Token": "op_test_token"},
            json={"player_name": "Ada Lovelace"},
        )
        assert start_resp.status_code == 200, start_resp.text
        session_id = start_resp.json()["session_id"]
        assert session_id == "st_fake_session_123"

        events_resp = client.get(
            f"/tools/sync/stadium/events/{session_id}",
            headers={"X-Operator-Token": "op_test_token"},
        )
        assert events_resp.status_code == 200

    events = _parse_sse(events_resp.text)
    names = [e for e, _ in events]
    assert names == ["gate_open", "gate_cleared", "done"], names

    gate_open_data = events[0][1]
    assert gate_open_data == {"gate_id": "g_01", "kind": "login", "hint": "Log in, then continue.", "url_host": "stadiumcompete.com"}

    done_data = events[2][1]
    # Exactly the shape StadiumSyncPanel.tsx's "done" handler destructures:
    # { status, matches, steps_used, error } (RELAY_ARCHITECTURE.md §8.2).
    assert done_data["status"] == "ok"
    assert done_data["steps_used"] == 5
    assert done_data["error"] is None
    assert done_data["matches"] == [
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

    # The bridge cleans up its per-session queue once the stream terminates.
    assert session_id not in backend_main._sync_event_queues


def test_stadium_sync_missing_key_rejected_before_any_relay_call(monkeypatch):
    monkeypatch.setenv("RELAY_BASE_URL", "https://relay.example.com")
    monkeypatch.setenv("RELAY_REGISTER_TOKEN", "rt_test_owner")
    monkeypatch.setenv("OPERATOR_TOKEN", "op_test_token")
    monkeypatch.setattr(backend_main, "BROWSER_AGENT_AVAILABLE", True)

    called = {"provisioned": False}

    async def fake_provision(register_token, *, relay_base_url):
        called["provisioned"] = True
        return "st_should_not_be_reached"

    monkeypatch.setattr(backend_main, "_provision_relay_session", fake_provision)

    with TestClient(backend_main.app) as client:
        resp = client.post(
            "/tools/sync/stadium",
            headers={"X-Operator-Token": "op_test_token"},
            json={"player_name": "Ada Lovelace"},
        )

    assert resp.status_code == 401
    assert called["provisioned"] is False


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
