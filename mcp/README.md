# OmniPong MCP server — one server, every MCP client

`omnipong_mcp_server.py` exposes the OmniPong actions as [Model Context
Protocol](https://modelcontextprotocol.io) tools over **stdio**, so any
MCP-capable agent can drive omnipong.com on demand.

Tools exposed:

| Tool | What it does |
| --- | --- |
| `check_new_tournaments(dry_run, limit)` | Scan for new area tournaments; create in-app alerts |
| `signup_tournament(title, events)` | **Real** tournament registration |
| `search_player(name)` | USATT id / rating / state lookup |
| `list_area_tournaments(deep)` | List area tournaments (optionally with events) |
| `sync_data()` | Full crawl into the local database |
| `get_my_matches()` | Pull the signed-in user's match history |

The server is transport-agnostic to the client: it pins its own working
directory to the repo root on startup, so every client behaves identically
regardless of where it launches the process from.

## Prerequisites (all clients)

1. The repo's virtualenv exists: `.venv/bin/python` (Python 3.13).
2. Dependencies installed: `.venv/bin/pip install -r requirements.txt` (needs
   `mcp` and `playwright`).
3. Browser installed once: `.venv/bin/playwright install chromium`.
4. Credentials in the repo's `.env`: `OMNIPONG_USER`, `OMNIPONG_PASS`.

Paths below use two placeholders. `ops/install_mcp.sh` replaces them with the
real absolute paths for this machine:

- `__PYTHON__` → `/abs/path/to/omnipong/.venv/bin/python`
- `__REPO__` → `/abs/path/to/omnipong`

### Automated install

```bash
./ops/install_mcp.sh            # configure every client detected on this machine
./ops/install_mcp.sh --client opencode
./ops/install_mcp.sh --dry-run  # show what would change, touch nothing
```

The installer backs up every file it edits, validates JSON before writing, and
is idempotent (re-running just refreshes the entry). Hermes' YAML is only
appended when no `mcp_servers:` key is already present; otherwise it prints the
snippet to add by hand.

## Per-client configuration

All snippets live in this folder as ready-to-paste templates.

### Claude Desktop

Config: `~/Library/Application Support/Claude/claude_desktop_config.json`
(macOS), `%APPDATA%\Claude\claude_desktop_config.json` (Windows),
`~/.config/Claude/claude_desktop_config.json` (Linux). Template:
`claude_desktop.json`.

```json
{
  "mcpServers": {
    "omnipong": {
      "command": "__PYTHON__",
      "args": ["__REPO__/omnipong_mcp_server.py"]
    }
  }
}
```

Restart Claude Desktop after editing.

### Claude Code

User scope (available in every project) lives in `~/.claude.json`; project scope
lives in `.mcp.json` at the project root. Template: `claude_code.mcp.json`.

```bash
claude mcp add --scope user omnipong -- __PYTHON__ __REPO__/omnipong_mcp_server.py
```

or paste into `.mcp.json`:

```json
{
  "mcpServers": {
    "omnipong": {
      "command": "__PYTHON__",
      "args": ["__REPO__/omnipong_mcp_server.py"]
    }
  }
}
```

Check with `claude mcp list`.

### opencode / OpenChamber

OpenChamber is built on the OpenCode agent and **shares OpenCode's config**, so
one entry covers both. Config: `~/.config/opencode/opencode.json` (global) or
`./opencode.json` (project). Template: `opencode.json`.

```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "omnipong": {
      "type": "local",
      "command": ["__PYTHON__", "__REPO__/omnipong_mcp_server.py"],
      "enabled": true
    }
  }
}
```

CLI: `opencode mcp add omnipong -- __PYTHON__ __REPO__/omnipong_mcp_server.py`.
In OpenChamber's GUI: **Settings → MCP → Add server → local**, then enter the
command. Restart the app/session so the server is picked up.

> Note: newer OpenCode builds nest servers under `mcp.servers`. If your version
> rejects the flat `mcp.omnipong` shape, wrap it: `{"mcp": {"servers": { ... }}}`.

### Hermes (NousResearch)

Config: `~/.hermes/config.yaml`, top-level `mcp_servers:` key. Template:
`hermes.yaml`.

```yaml
mcp_servers:
  omnipong:
    command: "__PYTHON__"
    args:
      - "__REPO__/omnipong_mcp_server.py"
```

### OpenClaw

Config: `~/.openclaw/openclaw.json`, `mcp.servers` key. Template:
`openclaw.json`.

```json
{
  "mcp": {
    "servers": {
      "omnipong": {
        "command": "__PYTHON__",
        "args": ["__REPO__/omnipong_mcp_server.py"]
      }
    }
  }
}
```

CLI: `openclaw mcp add omnipong --command __PYTHON__ --arg __REPO__/omnipong_mcp_server.py`,
then `openclaw mcp doctor omnipong --probe`.

## Verifying

Once registered and the app restarted, ask the assistant to run
`list_area_tournaments` (fast, read-only). If it fails with a login error, the
credentials in `.env` need refreshing — the tool call itself is working.
