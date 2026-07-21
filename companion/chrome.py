"""Find and launch the user's real Chrome with remote debugging enabled.

One method per function, per the owner's rule: if the platform/path can't be
resolved, raise a clean error — no silent fallback chains, no guessing.
"""
from __future__ import annotations

import os
import platform
import subprocess
import time
import urllib.request
import urllib.error
import json


def _candidate_chrome_paths() -> list[str]:
    system = platform.system()
    if system == "Darwin":
        return [
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            os.path.expanduser(
                "~/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
            ),
        ]
    if system == "Windows":
        program_files = os.environ.get("PROGRAMFILES", r"C:\Program Files")
        program_files_x86 = os.environ.get(
            "PROGRAMFILES(X86)", r"C:\Program Files (x86)"
        )
        local_app_data = os.environ.get("LOCALAPPDATA", "")
        candidates = [
            os.path.join(program_files, "Google", "Chrome", "Application", "chrome.exe"),
            os.path.join(program_files_x86, "Google", "Chrome", "Application", "chrome.exe"),
        ]
        if local_app_data:
            candidates.append(
                os.path.join(local_app_data, "Google", "Chrome", "Application", "chrome.exe")
            )
        return candidates
    raise RuntimeError(
        f"Unsupported platform '{system}'. The companion supports Windows and macOS only."
    )


def find_chrome_binary() -> str:
    """Return the path to the user's installed Chrome, or raise a clean error."""
    for path in _candidate_chrome_paths():
        if os.path.isfile(path):
            return path
    raise RuntimeError(
        "Could not find Google Chrome installed in any standard location. "
        "Install Chrome from https://www.google.com/chrome/ and try again."
    )


def dedicated_profile_dir() -> str:
    """A DEDICATED, rubberr-only Chrome profile directory — never the user's
    real/default Chrome profile (S2-profile hardening: the agent must never
    reach the user's everyday logged-in sites). The user logs into
    Stadium/USATT once inside this profile; it starts blank otherwise.

    Overridable via RUBBERR_CHROME_PROFILE_DIR for a custom location.
    """
    override = os.environ.get("RUBBERR_CHROME_PROFILE_DIR")
    if override:
        return override
    system = platform.system()
    if system == "Darwin":
        return os.path.expanduser("~/Library/Application Support/rubberr/chrome-profile")
    if system == "Windows":
        local_app_data = os.environ.get("LOCALAPPDATA", "")
        if not local_app_data:
            raise RuntimeError("LOCALAPPDATA environment variable is not set; cannot locate a profile directory.")
        return os.path.join(local_app_data, "rubberr", "chrome-profile")
    raise RuntimeError(f"Unsupported platform '{system}'. The companion supports Windows and macOS only.")


def is_chrome_debug_port_up(port: int, host: str = "127.0.0.1", timeout: float = 1.0) -> bool:
    """True if something is already answering CDP discovery on this port."""
    try:
        with urllib.request.urlopen(f"http://{host}:{port}/json/version", timeout=timeout) as resp:
            json.loads(resp.read().decode("utf-8"))
            return True
    except (urllib.error.URLError, ConnectionError, TimeoutError, ValueError):
        return False


def is_chrome_running() -> bool:
    """True if a Chrome process is running anywhere on this machine (any profile)."""
    system = platform.system()
    if system == "Darwin":
        result = subprocess.run(
            ["pgrep", "-f", "Google Chrome"], capture_output=True, text=True
        )
        return result.returncode == 0 and bool(result.stdout.strip())
    if system == "Windows":
        result = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq chrome.exe"],
            capture_output=True,
            text=True,
        )
        return "chrome.exe" in result.stdout.lower()
    raise RuntimeError(f"Unsupported platform '{system}'. The companion supports Windows and macOS only.")


def launch_chrome(port: int, wait_timeout: float = 20.0) -> subprocess.Popen | None:
    """Ensure Chrome is reachable on `port` with remote debugging enabled.

    Returns the launched Popen handle, or None if an already-running debug-enabled
    Chrome was reused (in which case the companion must NOT try to manage its
    lifecycle — it is the user's own browser).
    """
    if is_chrome_debug_port_up(port):
        print(f"[companion] Reusing your already-running Chrome (remote debugging already on port {port}).")
        return None

    # S2-profile: no need to ask the user to quit their everyday Chrome.
    # --user-data-dir locks are per-profile-directory, and the dedicated
    # rubberr profile (dedicated_profile_dir()) is never the same directory
    # as their regular Chrome — the two run as fully independent processes.

    binary = find_chrome_binary()
    user_data_dir = dedicated_profile_dir()
    os.makedirs(user_data_dir, exist_ok=True)
    print(f"[companion] Launching a DEDICATED rubberr Chrome profile ({user_data_dir}) with remote debugging on port {port}...")
    proc = subprocess.Popen(
        [
            binary,
            f"--remote-debugging-port={port}",
            f"--user-data-dir={user_data_dir}",
            "--no-first-run",
        ]
    )

    deadline = time.monotonic() + wait_timeout
    while time.monotonic() < deadline:
        if is_chrome_debug_port_up(port):
            return proc
        time.sleep(0.5)

    raise RuntimeError(
        f"Chrome launched (pid {proc.pid}) but did not open a debug port on {port} "
        f"within {wait_timeout}s. Check that no other process is bound to that port."
    )
