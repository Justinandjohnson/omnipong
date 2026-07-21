"""Self-check: proves the companion registers, proxies CDP, and completes a
gate round-trip -- WITHOUT a real relay or a real Chrome/login.

Spins up two local aiohttp servers:
  - a mock relay (WS endpoint at /companion/{token}, drives the test script)
  - a mock Chrome (HTTP /json/version + a devtools WS that echoes frames)

then runs the real Companion class against both and asserts each step of the
protocol in docs/RELAY_ARCHITECTURE.md §4 actually happens.

Run: python selfcheck.py
Exit code 0 = pass, non-zero = fail (with the failing assertion printed).
"""
from __future__ import annotations

import asyncio
import json
import re
import sys

from aiohttp import web, ClientSession, ClientTimeout, WSMsgType

import protocol as proto
from companion import Companion

RELAY_PORT = 18765
CHROME_PORT = 18766
GATE_UI_PORT = 18767

FAKE_WS_DEBUGGER_URL = f"ws://127.0.0.1:{CHROME_PORT}/devtools/browser/fake-id"


# ---------------------------------------------------------------------------
# Mock Chrome (the thing the companion proxies to)
# ---------------------------------------------------------------------------

async def mock_chrome_json_version(_request: web.Request) -> web.Response:
    return web.json_response({
        "Browser": "Chrome/999.0 (mock)",
        "webSocketDebuggerUrl": FAKE_WS_DEBUGGER_URL,
    })


async def mock_chrome_devtools_ws(request: web.Request) -> web.WebSocketResponse:
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    async for msg in ws:
        if msg.type == WSMsgType.TEXT:
            await ws.send_str(msg.data)  # echo — proves frames flow both ways
        elif msg.type in (WSMsgType.CLOSE, WSMsgType.ERROR):
            break
    return ws


def build_mock_chrome_app() -> web.Application:
    app = web.Application()
    app.router.add_get("/json/version", mock_chrome_json_version)
    app.router.add_get("/devtools/browser/fake-id", mock_chrome_devtools_ws)
    return app


# ---------------------------------------------------------------------------
# Mock relay: drives the whole test sequence as the "server side"
# ---------------------------------------------------------------------------

class CheckFailed(AssertionError):
    pass


async def _recv_json(ws: web.WebSocketResponse, expect_type: str) -> dict:
    msg = await asyncio.wait_for(ws.receive(), timeout=5)
    if msg.type != WSMsgType.TEXT:
        raise CheckFailed(f"expected TEXT ws message, got {msg.type}")
    data = json.loads(msg.data)
    if data.get("type") != expect_type:
        raise CheckFailed(f"expected message type {expect_type!r}, got {data.get('type')!r}: {data}")
    return data


async def mock_relay_companion_ws(request: web.Request) -> web.WebSocketResponse:
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    results: dict = request.app["results"]

    try:
        # 1. REGISTER
        reg = await _recv_json(ws, proto.REGISTER)
        assert reg["register_token"] == "selftest_token", reg
        assert reg["chrome_debug_port"] == CHROME_PORT, reg
        results["register"] = True
        await ws.send_str(json.dumps({
            "type": proto.REGISTER_OK, "user_id": "u_selftest", "heartbeat_interval_s": 30,
        }))

        # 2. CDP_HTTP_REQ proxy — companion must return the RAW body, unrewritten
        req_id = "h1"
        await ws.send_str(json.dumps({
            "type": proto.CDP_HTTP_REQ, "req_id": req_id, "path": "/json/version",
        }))
        res = await _recv_json(ws, proto.CDP_HTTP_RES)
        assert res["req_id"] == req_id, res
        assert res["status"] == 200, res
        assert res["body"]["webSocketDebuggerUrl"] == FAKE_WS_DEBUGGER_URL, res
        results["cdp_http_proxy"] = True

        # 3. CDP_WS_OPEN / FRAME / CLOSE proxy — round-trips through mock Chrome's echo
        channel = 1
        await ws.send_str(json.dumps({
            "type": proto.CDP_WS_OPEN, "channel": channel,
            "target_ws_path": "/devtools/browser/fake-id",
        }))
        opened = await _recv_json(ws, proto.CDP_WS_OPEN_OK)
        assert opened["channel"] == channel, opened

        frame_out = {"id": 7, "method": "Test.echo", "params": {"ping": "pong"}}
        await ws.send_str(json.dumps({
            "type": proto.CDP_WS_FRAME, "channel": channel, "data": frame_out,
        }))
        frame_in = await _recv_json(ws, proto.CDP_WS_FRAME)
        assert frame_in["channel"] == channel, frame_in
        assert frame_in["data"] == frame_out, frame_in
        results["cdp_ws_proxy"] = True

        await ws.send_str(json.dumps({"type": proto.CDP_WS_CLOSE, "channel": channel, "code": 1000}))

        # 4. Gate handshake — GATE_OPEN then a real HTTP POST /continue against the
        #    companion's local gate server (simulating the user clicking Continue),
        #    then expect GATE_CLEARED back over the tunnel.
        gate_id = "g_selftest"
        await ws.send_str(json.dumps({
            "type": proto.GATE_OPEN, "gate_id": gate_id, "kind": "login",
            "hint": "Log in on the mock site, then continue.", "url_host": "example.com",
        }))

        gate_url = f"http://127.0.0.1:{GATE_UI_PORT}/"
        async with ClientSession(timeout=ClientTimeout(total=1)) as client:
            page_html = None
            for _ in range(20):
                try:
                    async with client.get(gate_url) as resp:
                        if resp.status == 200:
                            page_html = await resp.text()
                            break
                except Exception:
                    await asyncio.sleep(0.25)
            if page_html is None:
                raise CheckFailed("companion's gate UI never came up on GATE_OPEN")
            # S4: /continue now requires the per-gate nonce embedded in the page
            # itself (CSRF fix) — pull it out the same way the page's own button
            # does, rather than posting blind like a forged cross-site request.
            nonce_match = re.search(r"X-Gate-Nonce':'([^']+)'", page_html)
            if not nonce_match:
                raise CheckFailed("gate UI page did not embed an X-Gate-Nonce")
            async with client.post(
                gate_url + "continue", headers={"X-Gate-Nonce": nonce_match.group(1)}
            ) as resp:
                assert resp.status == 200, f"gate /continue returned {resp.status}"

        cleared = await _recv_json(ws, proto.GATE_CLEARED)
        assert cleared["gate_id"] == gate_id, cleared
        results["gate_roundtrip"] = True

        # 5. Clean session end
        await ws.send_str(json.dumps({
            "type": proto.SESSION_ENDED, "session_id": "s_selftest", "reason": "completed",
        }))
        await asyncio.sleep(0.3)  # let companion process teardown before we close

    except CheckFailed as exc:
        results["error"] = str(exc)
    except Exception as exc:  # noqa: BLE001
        results["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        await ws.close()

    return ws


def build_mock_relay_app(results: dict) -> web.Application:
    app = web.Application()
    app["results"] = results
    app.router.add_get("/companion/{token}", mock_relay_companion_ws)
    return app


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

async def _run_server(app: web.Application, port: int) -> web.AppRunner:
    runner = web.AppRunner(app, access_log=None)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", port)
    await site.start()
    return runner


async def main() -> int:
    results: dict = {}

    relay_runner = await _run_server(build_mock_relay_app(results), RELAY_PORT)
    chrome_runner = await _run_server(build_mock_chrome_app(), CHROME_PORT)

    companion = Companion(
        relay_base_url=f"ws://127.0.0.1:{RELAY_PORT}",
        register_token="selftest_token",
        chrome_port=CHROME_PORT,
        gate_ui_port=GATE_UI_PORT,
        launch_chrome_on_start=False,  # mock Chrome above stands in for the real thing
    )

    try:
        await asyncio.wait_for(companion.run(), timeout=15)
    except asyncio.TimeoutError:
        results.setdefault("error", "companion.run() did not complete within 15s")
    finally:
        await relay_runner.cleanup()
        await chrome_runner.cleanup()

    checks = ["register", "cdp_http_proxy", "cdp_ws_proxy", "gate_roundtrip"]
    passed = [c for c in checks if results.get(c)]
    failed = [c for c in checks if not results.get(c)]

    print("\n--- companion self-check ---")
    for c in checks:
        print(f"  [{'PASS' if results.get(c) else 'FAIL'}] {c}")
    if "error" in results:
        print(f"  error: {results['error']}")

    if failed or "error" in results:
        print(f"\nSELF-CHECK FAILED ({len(passed)}/{len(checks)} passed)")
        return 1

    print(f"\nSELF-CHECK PASSED ({len(passed)}/{len(checks)})")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
