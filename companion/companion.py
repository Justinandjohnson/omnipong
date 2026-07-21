"""The Rubberr companion: runs on the end-user's machine.

Opens ONE outbound WebSocket to the relay, registers, then multiplexes the
relay's CDP requests to the user's own local Chrome (§1.3/§4.3 of
docs/RELAY_ARCHITECTURE.md), and handles the wait_for_human gate handshake
(§3/§4.4). No credentials are ever read, stored, or forwarded — the user logs
into sites themselves, in their own Chrome tab.

Usage:
    python companion.py --relay-base-url wss://relay.rubberr.example --register-token rt_xxx
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import signal
import sys

import aiohttp

import protocol as proto
from chrome import launch_chrome
from gate_ui import GateUI

log = logging.getLogger("companion")


class Companion:
    def __init__(
        self,
        relay_base_url: str,
        register_token: str,
        chrome_port: int = 9222,
        gate_ui_port: int = 8765,
        launch_chrome_on_start: bool = True,
    ) -> None:
        self.relay_base_url = relay_base_url.rstrip("/")
        self.register_token = register_token
        self.chrome_port = chrome_port
        self.launch_chrome_on_start = launch_chrome_on_start

        self._http = aiohttp.ClientSession()
        self._relay_ws: aiohttp.ClientWebSocketResponse | None = None
        self._channels: dict[int, aiohttp.ClientWebSocketResponse] = {}
        self._channel_tasks: dict[int, asyncio.Task] = {}
        self._relay_closed_channels: set[int] = set()
        self._heartbeat_task: asyncio.Task | None = None
        self._gate = GateUI(port=gate_ui_port)
        self._stopping = asyncio.Event()

    # ---- lifecycle -------------------------------------------------

    async def run(self) -> None:
        if self.launch_chrome_on_start:
            launch_chrome(self.chrome_port)

        url = f"{self.relay_base_url}/companion/{self.register_token}"
        log.info("connecting to relay: %s", url)
        async with self._http.ws_connect(url) as ws:
            self._relay_ws = ws
            await self._send(proto.REGISTER, {
                "register_token": self.register_token,
                "companion_version": proto.COMPANION_VERSION,
                "chrome_debug_port": self.chrome_port,
                "platform": sys.platform,
            })

            async for msg in ws:
                if msg.type != aiohttp.WSMsgType.TEXT:
                    continue
                try:
                    data = json.loads(msg.data)
                except json.JSONDecodeError:
                    log.warning("dropping non-JSON relay message")
                    continue
                await self._dispatch(data)
                if self._stopping.is_set():
                    break

        await self._teardown()

    async def _teardown(self) -> None:
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
        for task in self._channel_tasks.values():
            task.cancel()
        for ws in self._channels.values():
            if not ws.closed:
                await ws.close()
        self._gate.close()
        await self._http.close()

    async def stop(self) -> None:
        self._stopping.set()
        if self._relay_ws and not self._relay_ws.closed:
            await self._relay_ws.close()

    # ---- outbound helper --------------------------------------------

    async def _send(self, msg_type: str, fields: dict) -> None:
        assert self._relay_ws is not None
        await self._relay_ws.send_str(json.dumps({"type": msg_type, **fields}))

    # ---- dispatch ----------------------------------------------------

    async def _dispatch(self, msg: dict) -> None:
        msg_type = msg.get("type")

        if msg_type == proto.REGISTER_OK:
            log.info("registered as %s", msg.get("user_id"))
            print("[companion] Connected. An AI agent may now drive this Chrome window.")
            interval = msg.get("heartbeat_interval_s", 20)
            self._heartbeat_task = asyncio.create_task(self._heartbeat_loop(interval))

        elif msg_type == proto.REGISTER_REJECT:
            raise RuntimeError(f"Relay rejected registration: {msg.get('reason')}")

        elif msg_type == proto.SESSION_START:
            print(f"[companion] Session started: {msg.get('session_id')}")

        elif msg_type == proto.HEARTBEAT:
            pass  # relay's keepalive; our own heartbeat loop handles outbound side

        elif msg_type == proto.SESSION_ENDED:
            print(f"[companion] Session ended: {msg.get('reason')}")
            await self._close_all_channels()

        elif msg_type == proto.CDP_HTTP_REQ:
            asyncio.create_task(self._handle_cdp_http_req(msg))

        elif msg_type == proto.CDP_WS_OPEN:
            asyncio.create_task(self._handle_cdp_ws_open(msg))

        elif msg_type == proto.CDP_WS_FRAME:
            await self._handle_cdp_ws_frame(msg)

        elif msg_type == proto.CDP_WS_CLOSE:
            await self._handle_cdp_ws_close(msg)

        elif msg_type == proto.GATE_OPEN:
            asyncio.create_task(self._handle_gate_open(msg))

        elif msg_type == proto.GATE_TIMEOUT:
            print(f"[companion] Gate {msg.get('gate_id')} timed out.")
            self._gate.close()

        else:
            log.warning("unhandled relay message type: %s", msg_type)

    async def _heartbeat_loop(self, interval_s: float) -> None:
        try:
            while True:
                await asyncio.sleep(interval_s)
                await self._send(proto.HEARTBEAT, {})
        except asyncio.CancelledError:
            pass

    # ---- CDP HTTP discovery proxy (§4.3) ------------------------------

    async def _handle_cdp_http_req(self, msg: dict) -> None:
        req_id = msg["req_id"]
        path = msg["path"]
        url = f"http://127.0.0.1:{self.chrome_port}{path}"
        try:
            async with self._http.get(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                body = await resp.json(content_type=None)
                await self._send(proto.CDP_HTTP_RES, {
                    "req_id": req_id, "status": resp.status, "body": body,
                })
        except Exception as exc:  # noqa: BLE001 - report as a clean CDP error, no retry
            log.error("CDP_HTTP_REQ %s failed: %s", path, exc)
            await self._send(proto.CDP_HTTP_RES, {
                "req_id": req_id, "status": 502, "body": {"error": str(exc)},
            })

    # ---- CDP devtools websocket proxy (§4.3) --------------------------

    async def _handle_cdp_ws_open(self, msg: dict) -> None:
        channel = msg["channel"]
        target_path = msg["target_ws_path"]
        url = f"ws://127.0.0.1:{self.chrome_port}{target_path}"
        try:
            ws = await self._http.ws_connect(url, max_msg_size=0)
        except Exception as exc:  # noqa: BLE001
            log.error("CDP_WS_OPEN channel %s failed: %s", channel, exc)
            await self._send(proto.CDP_WS_CLOSE, {"channel": channel, "code": 1011})
            return

        self._channels[channel] = ws
        await self._send(proto.CDP_WS_OPEN_OK, {"channel": channel})
        self._channel_tasks[channel] = asyncio.create_task(self._pump_channel(channel, ws))

    async def _pump_channel(self, channel: int, ws: aiohttp.ClientWebSocketResponse) -> None:
        """Forward frames FROM local Chrome devtools TO the relay tunnel."""
        try:
            async for msg in ws:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    await self._send(proto.CDP_WS_FRAME, {
                        "channel": channel, "data": json.loads(msg.data),
                    })
                elif msg.type in (aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                    break
        except asyncio.CancelledError:
            pass
        finally:
            # Only notify the relay if the local Chrome side closed on its own —
            # if the relay already told us to close this channel, don't echo it back.
            if channel not in self._relay_closed_channels:
                await self._send(proto.CDP_WS_CLOSE, {"channel": channel, "code": 1000})
            self._relay_closed_channels.discard(channel)
            self._channels.pop(channel, None)
            self._channel_tasks.pop(channel, None)

    async def _handle_cdp_ws_frame(self, msg: dict) -> None:
        """Forward a frame FROM the relay TO local Chrome devtools."""
        channel = msg["channel"]
        ws = self._channels.get(channel)
        if ws is None or ws.closed:
            log.warning("CDP_WS_FRAME for unknown/closed channel %s", channel)
            return
        await ws.send_str(json.dumps(msg["data"]))

    async def _handle_cdp_ws_close(self, msg: dict) -> None:
        channel = msg["channel"]
        if channel not in self._channels:
            return
        self._relay_closed_channels.add(channel)
        ws = self._channels.get(channel)
        task = self._channel_tasks.get(channel)
        if ws and not ws.closed:
            await ws.close()
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    async def _close_all_channels(self) -> None:
        for channel in list(self._channels):
            await self._handle_cdp_ws_close({"channel": channel})

    # ---- gate handshake (§3/§4.4) --------------------------------------

    async def _handle_gate_open(self, msg: dict) -> None:
        gate_id = msg["gate_id"]
        await self._gate.wait_for_continue(
            gate_id=gate_id,
            kind=msg.get("kind", "unknown"),
            hint=msg.get("hint", "Please resolve this in your browser, then continue."),
            url_host=msg.get("url_host", ""),
        )
        await self._send(proto.GATE_CLEARED, {"gate_id": gate_id})
        print(f"[companion] Gate {gate_id} cleared — resuming.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Rubberr companion")
    parser.add_argument("--relay-base-url", required=True, help="e.g. wss://relay.rubberr.example")
    parser.add_argument("--register-token", required=True)
    parser.add_argument("--chrome-port", type=int, default=9222)
    parser.add_argument("--gate-ui-port", type=int, default=8765)
    parser.add_argument("--no-launch-chrome", action="store_true",
                         help="Don't launch/reuse Chrome (assumes it's already up on --chrome-port)")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING,
                         format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    companion = Companion(
        relay_base_url=args.relay_base_url,
        register_token=args.register_token,
        chrome_port=args.chrome_port,
        gate_ui_port=args.gate_ui_port,
        launch_chrome_on_start=not args.no_launch_chrome,
    )

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    def _handle_sigint(*_args):
        print("\n[companion] Shutting down (tunnel closes, relay reaps the session)...")
        loop.create_task(companion.stop())

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _handle_sigint)
        except NotImplementedError:
            pass  # Windows: no add_signal_handler; KeyboardInterrupt below covers Ctrl-C

    try:
        loop.run_until_complete(companion.run())
    except KeyboardInterrupt:
        loop.run_until_complete(companion.stop())
    finally:
        loop.close()


if __name__ == "__main__":
    main()
