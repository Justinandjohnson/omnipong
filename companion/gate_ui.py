"""Minimal local gate prompt (§3.2 / §3 of RELAY_ARCHITECTURE.md).

On GATE_OPEN the companion must show the user a clear local prompt telling them
to solve something (login / Cloudflare / captcha / 2FA) in their own Chrome tab,
then click Continue. One method: a tiny stdlib HTTP page on 127.0.0.1 — no GUI
toolkit dependency, works identically on Windows and macOS.
"""
from __future__ import annotations

import asyncio
import html
import secrets
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def _render_page(kind: str, hint: str, url_host: str, nonce: str) -> bytes:
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>Rubberr Agent — action needed</title>
<style>
  body {{ font-family: -apple-system, Segoe UI, sans-serif; max-width: 480px;
          margin: 10vh auto; text-align: center; color: #222; }}
  .badge {{ display: inline-block; background: #fee; color: #900; padding: 4px 10px;
            border-radius: 999px; font-size: 12px; font-weight: 600; letter-spacing: .04em; }}
  button {{ margin-top: 24px; font-size: 16px; padding: 12px 28px; border-radius: 8px;
            border: none; background: #111; color: #fff; cursor: pointer; }}
  button:hover {{ background: #333; }}
  code {{ background: #f2f2f2; padding: 2px 6px; border-radius: 4px; }}
</style></head>
<body>
  <div class="badge">AGENT ACTIVE — {html.escape(kind.upper())}</div>
  <h2>An AI agent is driving your browser</h2>
  <p>{html.escape(hint)}</p>
  <p>Site: <code>{html.escape(url_host)}</code></p>
  <p>Switch to your Chrome window, finish it there, then come back and click Continue.</p>
  <button onclick="fetch('/continue',{{method:'POST',headers:{{'X-Gate-Nonce':'{nonce}'}}}}).then(()=>document.body.innerHTML='<h2>Thanks — resuming...</h2>')">Continue</button>
</body></html>""".encode("utf-8")


class _GateServer(ThreadingHTTPServer):
    allow_reuse_address = True


class GateUI:
    """One gate prompt at a time, per the relay's one-session-per-companion model."""

    def __init__(self, host: str = "127.0.0.1", port: int = 8765):
        self._host = host
        self._port = port
        self._server: _GateServer | None = None
        self._thread: threading.Thread | None = None

    def open(self, gate_id: str, kind: str, hint: str, url_host: str, on_continue) -> None:
        """Show the prompt. `on_continue` is called (no args) from the server thread
        when the user clicks Continue — the caller is responsible for thread-safe
        hand-off (e.g. loop.call_soon_threadsafe) back into asyncio.

        S4: /continue requires a per-gate random nonce, generated here and
        embedded only in the page the user actually clicks — any other page's
        JS hitting /continue blind (CSRF) doesn't know it and is rejected.
        """
        nonce = secrets.token_urlsafe(24)
        page = _render_page(kind, hint, url_host, nonce)
        continued = threading.Event()
        expected_origin = f"http://{self._host}:{self._port}"

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args):
                pass  # keep stdout clean

            def do_GET(self):
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(page)

            def do_POST(self):
                if self.path != "/continue" or continued.is_set():
                    self.send_response(404)
                    self.end_headers()
                    return
                origin = self.headers.get("Origin") or self.headers.get("Referer") or ""
                if origin and not origin.startswith(expected_origin):
                    self.send_response(403)
                    self.end_headers()
                    return
                if self.headers.get("X-Gate-Nonce") != nonce:
                    self.send_response(403)
                    self.end_headers()
                    return
                continued.set()
                self.send_response(200)
                self.end_headers()
                on_continue()

        self._server = _GateServer((self._host, self._port), Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        url = f"http://{self._host}:{self._port}/"
        print(f"[companion] GATE OPEN ({kind}): {hint} — opening {url}")
        webbrowser.open(url)

    def close(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
        if self._thread is not None:
            self._thread.join(timeout=2)
            self._thread = None

    async def wait_for_continue(self, gate_id: str, kind: str, hint: str, url_host: str) -> None:
        """Async convenience wrapper: opens the prompt and awaits the Continue click."""
        loop = asyncio.get_running_loop()
        future: asyncio.Future[None] = loop.create_future()

        def _on_continue():
            loop.call_soon_threadsafe(lambda: future.done() or future.set_result(None))

        self.open(gate_id, kind, hint, url_host, _on_continue)
        try:
            await future
        finally:
            self.close()
