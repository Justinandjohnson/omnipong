# Rubberr Companion

The lightweight app you run on **your own machine** so a Rubberr AI agent can
drive a **DEDICATED, rubberr-only Chrome profile** — never your everyday
Chrome — to pull your private match data, with **nothing** (passwords,
cookies, OTPs) ever stored on our servers.

It does three things:
1. Opens (or reuses) a DEDICATED Chrome profile with remote debugging
   enabled, on `localhost:9222` only — see "The dedicated Chrome profile"
   below.
2. Opens **one** outbound connection to the relay and registers.
3. Multiplexes the relay's CDP traffic to your local Chrome, and shows a local
   "solve this, then Continue" prompt whenever the agent hits a login /
   Cloudflare / captcha / 2FA wall (see `docs/RELAY_ARCHITECTURE.md` §3).

## The dedicated Chrome profile (one-time login)

The companion launches Chrome with `--user-data-dir` pointed at a profile
directory that belongs to rubberr alone (`chrome.py: dedicated_profile_dir()`
— defaults to `~/Library/Application Support/rubberr/chrome-profile` on
macOS, `%LOCALAPPDATA%\rubberr\chrome-profile` on Windows; override with the
`RUBBERR_CHROME_PROFILE_DIR` env var). This is a **separate, blank Chrome
profile** — it starts with no history, no cookies, no saved logins from your
regular browsing.

**The first time you run the companion**, that dedicated profile opens
empty. Log into Stadium (or USATT, OmniPong, whichever site you're syncing)
**in that window, once** — the same as signing into a browser on a brand new
computer. Chrome remembers that session in the dedicated profile's own
storage, so you generally only have to do this once; the agent reuses that
login on later syncs the same way your everyday Chrome remembers you're
signed in.

Because it's a separate `--user-data-dir`, the agent can **never** reach
anything logged into your everyday Chrome — different profile directory,
different cookie jar, different saved passwords. Quitting or leaving your
regular Chrome open makes no difference either way; the two run as fully
independent processes.

Full protocol details: `../docs/RELAY_ARCHITECTURE.md`.

## Requirements

- Python 3.10+
- Google Chrome installed (standard location)
- Windows or macOS

## Setup

### macOS

```bash
cd companion
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Windows (PowerShell)

```powershell
cd companion
py -3 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Run

You'll be given a `register_token` when you start a Rubberr sync from the
frontend (or the relay operator gives you one for testing). Then:

### macOS

```bash
source .venv/bin/activate
python companion.py --relay-base-url wss://relay.rubberr.example --register-token rt_xxx
```

### Windows (PowerShell)

```powershell
.venv\Scripts\Activate.ps1
python companion.py --relay-base-url wss://relay.rubberr.example --register-token rt_xxx
```

What happens next:
- If a debug-enabled Chrome is already up on the configured port, the companion reuses it —
  this is the ONLY case where it doesn't launch its own.
- Otherwise it launches Chrome pointed at the DEDICATED rubberr profile (see above) with
  debugging enabled. Your everyday Chrome, if open, is left completely alone — no need to
  quit it.
- The companion prints `Connected. An AI agent may now drive this Chrome window.` once
  registered — that message, plus the local gate page whenever it opens, are the "agent is
  active" indicators required by the relay spec (§5 blast-radius rule).
- The FIRST time, log into whatever site you want synced (Stadium, USATT, etc.) in that
  dedicated Chrome window yourself — see "The dedicated Chrome profile" above. After that,
  the profile remembers your session the same way any browser does.
- If the agent hits a login/Cloudflare/2FA/captcha wall, your default browser opens a small
  local page (`http://127.0.0.1:8765`) explaining what to do. Solve it **in your Chrome tab**,
  then click **Continue** on that local page. Nothing about what you typed ever leaves your
  machine — only the fact that you clicked Continue is sent back.
- Press `Ctrl-C` to stop the companion at any time. This closes the tunnel; the relay reaps
  your session immediately. Your Chrome window is left open — the companion never closes your
  browser for you.

### Flags

| Flag | Default | Meaning |
|---|---|---|
| `--relay-base-url` | (required) | e.g. `wss://relay.rubberr.example` |
| `--register-token` | (required) | one-time token identifying you to the relay |
| `--chrome-port` | `9222` | local Chrome remote-debugging port |
| `--gate-ui-port` | `8765` | local port for the "solve this, then Continue" page |
| `--no-launch-chrome` | off | skip Chrome discovery/launch (assumes it's already up) |
| `-v` / `--verbose` | off | debug logging |

## Self-check (no real relay, no real login needed)

Proves registration, CDP HTTP-discovery proxying, CDP websocket frame
proxying, and the gate open/Continue round-trip all work, against a local
mock relay + mock Chrome:

```bash
python selfcheck.py
```

Exit code `0` and `SELF-CHECK PASSED (4/4)` means: the companion correctly
speaks the relay protocol end-to-end. It does **not** exercise a real Chrome
launch or a real login — see Cross-platform caveats below for what that
leaves unverified.

## Cross-platform caveats (what is NOT verified by the self-check)

- **Chrome discovery paths** (`chrome.py: _candidate_chrome_paths`) are the
  standard install locations for Chrome on Windows/macOS. A non-standard
  install location will raise a clean `RuntimeError` rather than silently
  failing — but it has only been code-reviewed, not run, on Windows.
- **"Chrome already running" detection** uses `tasklist` on Windows and
  `pgrep` on macOS. Neither was exercised against a real running Chrome in
  this build pass — only the debug-port-already-up path (`is_chrome_debug_port_up`)
  was implicitly covered by the self-check's mock HTTP server.
- **Real gate solving** (an actual Cloudflare challenge / login form / 2FA
  prompt) was not exercised — the self-check simulates the round-trip with a
  scripted POST to `/continue`, not an actual human clicking a real button in
  a real browser window.
- **Default browser popup** (`webbrowser.open()` in `gate_ui.py`) depends on
  the OS having a registered default browser handler; not exercised headless.

If you want these verified, run the companion for real against a live relay
and a live Chrome — the self-check only proves the protocol plumbing, not the
physical machine interactions.
