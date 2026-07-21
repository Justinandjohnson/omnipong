"""Self-check for the relay — runs the real ASGI app in-process (Starlette's
TestClient, which drives real WebSocket handshakes and real HTTP requests
against `server.app`, no mocked internals) and exercises the full
register -> session/start -> CDP discovery -> CDP devtools frame ->
session/stop path end-to-end.

This is intentionally NOT a real browser and NOT a real second machine: it
plays the companion role itself over a WebSocket, exactly the way a real
companion process would, so every relay code path (tunnel dispatch, HTTP
discovery proxy + rewrite, devtools channel multiplex, gate handshake,
session teardown) actually executes. What it does NOT prove is documented
at the bottom of this file and in the build report.

Run directly:
    .venv/bin/python -m pytest test_relay.py -v
or:
    .venv/bin/python test_relay.py
"""

from __future__ import annotations

import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor

import pytest
from starlette.testclient import TestClient

import config
import protocol as P
import server

REGISTER_TOKEN = "rt_test_token_0001"
USER_ID = "u_test_0001"

# S3 hardening: /session/start, /session/stop, /session/gate now require an
# operator token (RELAY_OPERATOR_TOKEN / X-Operator-Token header, server.py's
# _require_operator_token). Every test that calls those endpoints must send
# this header — a handful of tests below specifically exercise the gate
# itself (missing header, unconfigured token) without it.
OPERATOR_TOKEN = "op_test_token_0001"
OP_HEADERS = {"X-Operator-Token": OPERATOR_TOKEN}


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(config, "OPERATOR_TOKEN", OPERATOR_TOKEN)
    # Enter the TestClient context first — this fires the FastAPI startup
    # event, which loads register_tokens.json from disk (normally empty in
    # this checkout). Only after that do we inject the test token, so it
    # isn't clobbered by the startup reload.
    with TestClient(server.app) as c:
        server.registry.load_register_tokens({REGISTER_TOKEN: USER_ID})
        yield c
    # Reset shared registry state between tests.
    server.registry.__init__()  # type: ignore[misc]


def test_health(client: TestClient):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_register_reject_bad_token(client: TestClient):
    with client.websocket_connect("/companion/rt_totally_bogus") as ws:
        msg = json.loads(ws.receive_text())
        assert msg["type"] == P.REGISTER_REJECT
        assert msg["reason"] == "bad_token"


def test_session_start_requires_online_companion(client: TestClient):
    resp = client.post("/session/start", json={"register_token": REGISTER_TOKEN}, headers=OP_HEADERS)
    assert resp.status_code == 404
    assert resp.json()["error"]["type"] == "CompanionNotOnline"


def test_session_start_rejects_bare_user_id_without_register_token(client: TestClient):
    """S3: a caller-supplied user_id must never mint a session on its own —
    only a valid register_token, resolved to a user_id server-side, can."""
    resp = client.post("/session/start", json={"user_id": USER_ID}, headers=OP_HEADERS)
    assert resp.status_code == 400
    assert "register_token" in resp.json()["detail"]


def test_session_start_requires_operator_token(client: TestClient):
    """S3: /session/start is owner-only — no operator header, no session."""
    resp = client.post("/session/start", json={"register_token": REGISTER_TOKEN})
    assert resp.status_code == 401
    assert resp.json()["error"]["type"] == "BadOperatorToken"


def test_session_start_fails_closed_when_operator_token_unconfigured(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
):
    """S1/S3: if RELAY_OPERATOR_TOKEN is unset, control endpoints must refuse
    (503) rather than run open — even with a header supplied."""
    monkeypatch.setattr(config, "OPERATOR_TOKEN", None)
    resp = client.post(
        "/session/start", json={"register_token": REGISTER_TOKEN}, headers=OP_HEADERS
    )
    assert resp.status_code == 503
    assert resp.json()["error"]["type"] == "OperatorTokenNotConfigured"


def test_full_happy_path_register_session_cdp_stop(client: TestClient):
    with client.websocket_connect(f"/companion/{REGISTER_TOKEN}") as companion_ws:
        companion_ws.send_text(
            json.dumps(
                {
                    "type": P.REGISTER,
                    "register_token": REGISTER_TOKEN,
                    "companion_version": "0.1.0-test",
                    "chrome_debug_port": 9222,
                    "platform": "darwin",
                }
            )
        )
        reg_ok = json.loads(companion_ws.receive_text())
        assert reg_ok["type"] == P.REGISTER_OK
        assert reg_ok["user_id"] == USER_ID
        assert reg_ok["heartbeat_interval_s"] == config.HEARTBEAT_INTERVAL_S

        # --- /session/start ---
        resp = client.post("/session/start", json={"register_token": REGISTER_TOKEN}, headers=OP_HEADERS)
        assert resp.status_code == 200, resp.text
        session = resp.json()
        session_token = session["session_token"]
        assert session["session_id"].startswith("s_")
        assert session_token.startswith("st_")

        session_start_msg = json.loads(companion_ws.receive_text())
        assert session_start_msg == {"type": P.SESSION_START, "session_id": session["session_id"]}

        # --- second session for same user without takeover -> 409 ---
        conflict = client.post("/session/start", json={"register_token": REGISTER_TOKEN}, headers=OP_HEADERS)
        assert conflict.status_code == 409
        assert conflict.json()["error"]["type"] == "SessionConflict"

        # --- CDP HTTP discovery facade (§1.1/§1.2), fake companion answers ---
        # The GET blocks server-side on a companion round trip, so issue it on
        # a worker thread while this thread plays "companion" on companion_ws.
        with ThreadPoolExecutor(max_workers=1) as pool:
            fut = pool.submit(client.get, f"/cdp/{session_token}/json/version")

            discovery_req = json.loads(companion_ws.receive_text())
            assert discovery_req["type"] == P.CDP_HTTP_REQ
            assert discovery_req["path"] == "/json/version"

            fake_chrome_body = {
                "Browser": "Chrome/999.0.0.0",
                "webSocketDebuggerUrl": "ws://localhost:9222/devtools/browser/FAKE-BROWSER-ID",
            }
            companion_ws.send_text(
                json.dumps(
                    {
                        "type": P.CDP_HTTP_RES,
                        "req_id": discovery_req["req_id"],
                        "status": 200,
                        "body": fake_chrome_body,
                    }
                )
            )
            discovery_resp = fut.result(timeout=5)

        assert discovery_resp.status_code == 200
        rewritten = discovery_resp.json()
        # Load-bearing assertion: host rewritten to the relay, path preserved,
        # session_token folded into the relay path (§1.1).
        assert rewritten["webSocketDebuggerUrl"] == (
            f"ws://testserver/cdp/{session_token}/devtools/browser/FAKE-BROWSER-ID"
        )
        assert rewritten["Browser"] == "Chrome/999.0.0.0"  # untouched passthrough field

        # --- CDP devtools websocket multiplex (§1.3/§4.3) ---
        devtools_path = f"/cdp/{session_token}/devtools/browser/FAKE-BROWSER-ID"
        with client.websocket_connect(devtools_path) as agent_ws:
            ws_open = json.loads(companion_ws.receive_text())
            assert ws_open["type"] == P.CDP_WS_OPEN
            assert ws_open["channel"] == 1
            assert ws_open["target_ws_path"] == "/devtools/browser/FAKE-BROWSER-ID"
            companion_ws.send_text(json.dumps({"type": P.CDP_WS_OPEN_OK, "channel": 1}))

            # Agent sends a fake CDP command frame.
            cdp_command = {"id": 7, "method": "Page.navigate", "params": {"url": "https://example.com"}}
            agent_ws.send_text(json.dumps(cdp_command))

            frame_out = json.loads(companion_ws.receive_text())
            assert frame_out["type"] == P.CDP_WS_FRAME
            assert frame_out["channel"] == 1
            assert frame_out["data"] == cdp_command  # forwarded byte-for-byte, unmodified (§5)

            # "Chrome" (companion) answers.
            cdp_reply = {"id": 7, "result": {"frameId": "FAKE-FRAME"}}
            companion_ws.send_text(
                json.dumps({"type": P.CDP_WS_FRAME, "channel": 1, "data": cdp_reply})
            )
            reply_in = json.loads(agent_ws.receive_text())
            assert reply_in == cdp_reply

            # --- gate handshake round trip (§3/§4.4), independent of the CDP channel ---
            gate_resp = client.post(
                "/session/gate",
                json={
                    "session_token": session_token,
                    "gate_id": "g_test_1",
                    "kind": "login",
                    "hint": "Log in to Stadium, then click Continue",
                    "url_host": "stadiumcompete.com",
                },
                headers=OP_HEADERS,
            )
            assert gate_resp.status_code == 202

            gate_open = json.loads(companion_ws.receive_text())
            assert gate_open == {
                "type": P.GATE_OPEN,
                "gate_id": "g_test_1",
                "kind": "login",
                "hint": "Log in to Stadium, then click Continue",
                "url_host": "stadiumcompete.com",
            }

            companion_ws.send_text(json.dumps({"type": P.GATE_CLEARED, "gate_id": "g_test_1"}))

            # Bounded poll on the gate-wait convenience endpoint (§ session/gate/.../wait)
            # rather than the raw /session/events SSE stream: httpx's ASGI test
            # transport buffers a streaming response until its generator returns,
            # and our SSE generator intentionally stays open for the life of the
            # session — so it is exercised in its own short, bounded test below
            # instead of inline here.
            wait_resp = client.get(f"/session/gate/{session_token}/g_test_1/wait")
            assert wait_resp.json() == {"type": P.GATE_CLEARED, "gate_id": "g_test_1"}

            # --- /session/stop tears everything down cleanly ---
            stop_resp = client.post("/session/stop", json={"session_token": session_token}, headers=OP_HEADERS)
            assert stop_resp.status_code == 200
            assert stop_resp.json()["status"] == "stopped"

            session_ended = json.loads(companion_ws.receive_text())
            assert session_ended == {
                "type": P.SESSION_ENDED,
                "session_id": session["session_id"],
                "reason": P.REASON_COMPLETED,
            }

            # Agent's devtools websocket must be closed by the relay on teardown.
            with pytest.raises(Exception):
                agent_ws.receive_text()

        # After stop, the session_token is dead — a fresh gate/HTTP call fails clean.
        after = client.get(f"/cdp/{session_token}/json/version")
        assert after.status_code == 404
        assert after.json()["error"]["type"] == "UnknownSession"


def test_gate_timeout_short_ttl(monkeypatch: pytest.MonkeyPatch, client: TestClient):
    """GATE_TTL fires and emits GATE_TIMEOUT if the companion never clears it."""
    monkeypatch.setattr(config, "GATE_TTL_S", 1)

    with client.websocket_connect(f"/companion/{REGISTER_TOKEN}") as companion_ws:
        companion_ws.send_text(json.dumps({"type": P.REGISTER, "register_token": REGISTER_TOKEN}))
        json.loads(companion_ws.receive_text())  # REGISTER_OK

        resp = client.post("/session/start", json={"register_token": REGISTER_TOKEN}, headers=OP_HEADERS)
        session = resp.json()
        session_token = session["session_token"]
        json.loads(companion_ws.receive_text())  # SESSION_START

        client.post(
            "/session/gate",
            json={
                "session_token": session_token,
                "gate_id": "g_timeout",
                "kind": "cloudflare",
                "hint": "solve it",
                "url_host": "example.com",
            },
            headers=OP_HEADERS,
        )
        json.loads(companion_ws.receive_text())  # GATE_OPEN

        wait_resp = client.get(f"/session/gate/{session_token}/g_timeout/wait")
        assert wait_resp.json()["type"] == P.GATE_TIMEOUT

        timeout_to_companion = json.loads(companion_ws.receive_text())
        assert timeout_to_companion == {"type": P.GATE_TIMEOUT, "gate_id": "g_timeout"}


def test_idle_timeout_suppressed_during_open_gate(monkeypatch: pytest.MonkeyPatch, client: TestClient):
    """C1: no CDP frames flow while a gate is open (by design), so the idle
    watcher must not reap the session on IDLE_TTL_S during that window —
    GATE_TTL_S governs it instead. Verifies both halves: an open gate
    survives past IDLE_TTL_S with zero CDP activity, and the gate itself
    still times out on schedule if nobody clears it."""
    # GATE_TTL_S must outlast the idle watcher's first tick (every 5s) so
    # that tick lands while the gate is still open — otherwise the gate
    # would already have timed out (clearing open_gate_ids) before the idle
    # watcher gets a chance to check, and the test would prove nothing.
    monkeypatch.setattr(config, "IDLE_TTL_S", 1)
    monkeypatch.setattr(config, "GATE_TTL_S", 7)

    with client.websocket_connect(f"/companion/{REGISTER_TOKEN}") as companion_ws:
        companion_ws.send_text(json.dumps({"type": P.REGISTER, "register_token": REGISTER_TOKEN}))
        json.loads(companion_ws.receive_text())  # REGISTER_OK

        resp = client.post("/session/start", json={"register_token": REGISTER_TOKEN}, headers=OP_HEADERS)
        session = resp.json()
        session_token = session["session_token"]
        json.loads(companion_ws.receive_text())  # SESSION_START

        client.post(
            "/session/gate",
            json={
                "session_token": session_token,
                "gate_id": "g_idle",
                "kind": "login",
                "hint": "log in",
                "url_host": "example.com",
            },
            headers=OP_HEADERS,
        )
        json.loads(companion_ws.receive_text())  # GATE_OPEN

        # The idle watcher's first tick lands at t=5s — past IDLE_TTL_S (1s)
        # with zero CDP activity the whole time. The pre-fix code would have
        # reaped this session on that tick; the gate (GATE_TTL_S=7s) is still
        # open at that point, so it must not.
        time.sleep(6)
        assert server.registry.get_session(session_token) is not None  # still alive, no UnknownSession

        # The unsolved gate still times out on its own clock (~t=7s),
        # independent of the idle watcher.
        timeout_to_companion = json.loads(companion_ws.receive_text())
        assert timeout_to_companion == {"type": P.GATE_TIMEOUT, "gate_id": "g_idle"}


def test_session_events_404_after_session_ends(client: TestClient):
    """/session/events is only addressable while the session is live.

    NOTE: this does not drive the SSE stream to a live client — httpx's ASGI
    test transport buffers a StreamingResponse until its generator returns,
    and our SSE generator intentionally stays open for the session's
    lifetime, so a real incremental read isn't exercisable from this
    in-process harness (see build report / "not verified" list). What *is*
    exercised end-to-end, in test_full_happy_path_register_session_cdp_stop,
    is the producer side: _dispatch_companion_message pushing a GATE_CLEARED
    event onto session.events on the same asyncio.Queue this endpoint reads.
    """
    with client.websocket_connect(f"/companion/{REGISTER_TOKEN}") as companion_ws:
        companion_ws.send_text(json.dumps({"type": P.REGISTER, "register_token": REGISTER_TOKEN}))
        json.loads(companion_ws.receive_text())  # REGISTER_OK

        resp = client.post("/session/start", json={"register_token": REGISTER_TOKEN}, headers=OP_HEADERS)
        session = resp.json()
        session_token = session["session_token"]
        json.loads(companion_ws.receive_text())  # SESSION_START

        client.post("/session/stop", json={"session_token": session_token}, headers=OP_HEADERS)
        json.loads(companion_ws.receive_text())  # SESSION_ENDED to companion

        resp = client.get(f"/session/events/{session_token}")
        assert resp.status_code == 404  # session already reaped from sessions_by_token


def test_heartbeat_miss_force_closes_companion(monkeypatch: pytest.MonkeyPatch, client: TestClient):
    """A companion that stops sending HEARTBEAT gets force-closed, tearing
    down its bound session with reason=companion_gone — the F1 failure mode,
    triggered by the heartbeat watcher rather than a real socket drop."""
    monkeypatch.setattr(config, "HEARTBEAT_INTERVAL_S", 0.2)
    monkeypatch.setattr(config, "HEARTBEAT_MISS_LIMIT_S", 0.4)

    with client.websocket_connect(f"/companion/{REGISTER_TOKEN}") as companion_ws:
        companion_ws.send_text(json.dumps({"type": P.REGISTER, "register_token": REGISTER_TOKEN}))
        json.loads(companion_ws.receive_text())  # REGISTER_OK

        resp = client.post("/session/start", json={"register_token": REGISTER_TOKEN}, headers=OP_HEADERS)
        session = resp.json()
        json.loads(companion_ws.receive_text())  # SESSION_START

        # Go silent — no HEARTBEAT, no further sends. The watcher force-
        # closes the tunnel; the companion side observes that as a close.
        with pytest.raises(Exception):
            companion_ws.receive_text()

    # The bound session must have been torn down as companion_gone.
    resp = client.get(f"/cdp/{session['session_token']}/json/version")
    assert resp.status_code == 404
    assert resp.json()["error"]["type"] == "UnknownSession"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
