"""
S1 hardening — owner-only operator gate on the Tier-3 sync + Tier-1 lookup
endpoints: POST /tools/sync/stadium, GET /tools/sync/stadium/events/{id},
POST /tools/sync/omnipong, GET /tools/sync/omnipong/events/{id}, and
GET /tools/lookup/usatt.

Proves the gate (main.py's `_require_operator_token`) runs BEFORE any other
endpoint logic (BYOK check, relay session provisioning, browser_agent call):
  - OPERATOR_TOKEN unset on the server -> 503, fails CLOSED (never runs open).
  - OPERATOR_TOKEN set, no/wrong X-Operator-Token header -> 401.
  - OPERATOR_TOKEN set, correct header -> gate passes (falls through to the
    endpoint's normal next check, e.g. the BYOK 401 for sync endpoints or a
    clean 500 for the lookup endpoint once RELAY_BASE_URL is also unset —
    proving the gate is not blocking correct callers, without needing to
    stand up a real relay + browser agent for this test).

No real browser, relay, or Chrome — same isolation approach as
test_sync_sse_integration.py.

Run: python -m pytest rubberr/backend/tests/test_operator_gate.py -v
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_DIR.parent.parent

sys.modules.setdefault("playwright", MagicMock())
sys.modules.setdefault("playwright.async_api", SimpleNamespace(async_playwright=MagicMock()))
sys.modules.setdefault("openai", SimpleNamespace(OpenAI=MagicMock()))

sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(BACKEND_DIR))

from fastapi.testclient import TestClient  # noqa: E402

from rubberr.backend import main as backend_main  # noqa: E402

# (method, path) for every endpoint S1 gates. Events endpoints use a
# placeholder session_id — the gate must reject before that id is ever
# looked up, so it doesn't need to be real.
_GATED_ENDPOINTS = [
    ("POST", "/tools/sync/stadium"),
    ("GET", "/tools/sync/stadium/events/st_placeholder"),
    ("POST", "/tools/sync/omnipong"),
    ("GET", "/tools/sync/omnipong/events/st_placeholder"),
    ("GET", "/tools/lookup/usatt?name=Ada+Lovelace"),
]


def _call(client: TestClient, method: str, path: str, headers: dict | None = None):
    if method == "POST":
        return client.post(path, headers=headers or {}, json={"player_name": "Ada Lovelace"})
    return client.get(path, headers=headers or {})


@pytest.mark.parametrize("method,path", _GATED_ENDPOINTS)
def test_fails_closed_when_operator_token_unconfigured(monkeypatch, method, path):
    """OPERATOR_TOKEN unset on the server -> 503, even with a header sent."""
    monkeypatch.delenv("OPERATOR_TOKEN", raising=False)
    with TestClient(backend_main.app) as client:
        resp = _call(client, method, path, headers={"X-Operator-Token": "anything"})
    assert resp.status_code == 503, resp.text
    assert "OPERATOR_TOKEN" in resp.json()["detail"]


@pytest.mark.parametrize("method,path", _GATED_ENDPOINTS)
def test_rejects_missing_operator_header(monkeypatch, method, path):
    monkeypatch.setenv("OPERATOR_TOKEN", "op_correct_token")
    with TestClient(backend_main.app) as client:
        resp = _call(client, method, path)
    assert resp.status_code == 401, resp.text


@pytest.mark.parametrize("method,path", _GATED_ENDPOINTS)
def test_rejects_wrong_operator_header(monkeypatch, method, path):
    monkeypatch.setenv("OPERATOR_TOKEN", "op_correct_token")
    with TestClient(backend_main.app) as client:
        resp = _call(client, method, path, headers={"X-Operator-Token": "op_wrong_token"})
    assert resp.status_code == 401, resp.text


def test_correct_operator_token_passes_the_gate(monkeypatch):
    """With the right header, the gate lets the request through to the
    endpoint's own next check — proven here by the BYOK 401 that normally
    follows a missing X-User-Api-Key on /tools/sync/stadium (not a gate
    401/503), showing the operator gate itself did not block it."""
    monkeypatch.setenv("OPERATOR_TOKEN", "op_correct_token")
    monkeypatch.setenv("RELAY_BASE_URL", "https://relay.example.com")
    monkeypatch.setenv("RELAY_REGISTER_TOKEN", "rt_test_owner")
    monkeypatch.setattr(backend_main, "BROWSER_AGENT_AVAILABLE", True)

    with TestClient(backend_main.app) as client:
        resp = client.post(
            "/tools/sync/stadium",
            headers={"X-Operator-Token": "op_correct_token"},
            json={"player_name": "Ada Lovelace"},
        )
    assert resp.status_code == 401, resp.text
    assert "X-User-Api-Key" in resp.json()["detail"]


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
