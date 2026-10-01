# OmniPong Agent

One interface for everything the project does against omnipong.com, plus a
daily scout that watches your area for new tournaments and asks (in-app)
whether to sign you up.

## Pieces

| File | Role |
|---|---|
| `omnipong_config.py` | Area rules (`AREA_REGION`, `AREA_CITIES`, `AREA_STATES`) — no more hard-coded cities. |
| `omnipong_agent.py` | The action surface: `check`, `signup`, `search`, `sync`, `matches`, `tournaments`. CLI + `run_action()` API. |
| `daily_check.py` | Daily scout. Finds new area tournaments, builds an AI recommendation, writes a `Notification`. |
| `omnipong_mcp_server.py` | Exposes those actions as MCP tools for any MCP-capable agent. |
| `rubberr/frontend/src/app/agent/page.tsx` | The **Agent** tab route in the Rubberr app. |
| `rubberr/frontend/src/components/AgentConsole.tsx` | The tab UI — pick an action, run it via `POST /agent/action`. |
| `ops/install_mcp.sh` | Registers the MCP server in every installed client (see `mcp/README.md`). |
| `ops/install_daily_check.sh` | Installs the macOS launchd job that runs the scout daily. |
| `tests/test_omnipong_agent.py` | Offline tests for area matching + action/MCP wiring. |

## The daily loop

```
launchd 09:00 → daily_check.py
   login → scrape tournaments → filter to area → for each NOT-yet-alerted one:
       scrape its events → AI recommendation → Notification(type="new_tournament")
   → Rubberr dashboard AIAlertPopup shows "Sign Up with AI?"
   → POST /tournaments/signup → OmniPongScraper.signup_for_tournament → registered
```

Only **new** tournaments get the expensive deep scrape and an alert. Already
alerted ones are skipped, so the run is fast and you're never pinged twice
about the same event. Notifications are the delivery channel (the project uses
in-app only — no email/SMS).

## CLI

```bash
.venv/bin/python omnipong_agent.py check                 # daily scout
.venv/bin/python omnipong_agent.py check --dry-run       # report only, write nothing
.venv/bin/python omnipong_agent.py tournaments --deep    # list area tournaments + events
.venv/bin/python omnipong_agent.py signup --title "Spring Open" --event "Open Singles"
.venv/bin/python omnipong_agent.py search --name "Justin Johnson"
.venv/bin/python omnipong_agent.py sync                  # full crawl into the DB
.venv/bin/python omnipong_agent.py matches               # my match history
```

## MCP

```bash
.venv/bin/python omnipong_mcp_server.py
```

Register with an MCP client:

```json
{
  "mcpServers": {
    "omnipong": {
      "command": "/Users/you/Desktop/omnipong/.venv/bin/python",
      "args": ["/Users/you/Desktop/omnipong/omnipong_mcp_server.py"]
    }
  }
}
```

Tools: `check_new_tournaments`, `signup_tournament`, `search_player`,
`list_area_tournaments`, `sync_data`, `get_my_matches`.

One-shot installer for all installed clients (Claude Desktop, Claude Code,
opencode/OpenChamber, OpenClaw, Hermes) — see `mcp/README.md`:

```bash
ops/install_mcp.sh --dry-run   # preview
ops/install_mcp.sh             # write (each file backed up first)
```

## GUI — the Rubberr "Agent" tab

The app ships the same capability as the MCP. The `/agent` tab
(`AgentConsole.tsx`) posts to the backend:

```
POST /agent/action  { "action": "check", "params": { "dry_run": true } }
GET  /agent/actions          # lists the six action names
```

Both the tab and the MCP server call `omnipong_agent.run_action()` — one code
path, so the GUI and any MCP client can never drift apart.

## Scheduling

See `ops/README.md`. Short version:

```bash
ops/install_daily_check.sh                 # daily 09:00
launchctl kickstart -k gui/$(id -u)/com.omnipong.dailycheck   # run now
```

## Safety notes

- `signup_tournament` performs a **real registration** (accepts the waiver,
  picks events). The UI gates it behind a user click; the MCP tool runs it
  directly, so only point MCP clients you trust at it.
- `check --dry-run` is the safe way to see what the scout would alert on.
- Credentials come from `.env` (`OMNIPONG_USER` / `OMNIPONG_PASS`); nothing
  personal is hard-coded in the new code.

## Tests

```bash
.venv/bin/python -m pytest tests/test_omnipong_agent.py -q
```

No network/browser/DB needed.
