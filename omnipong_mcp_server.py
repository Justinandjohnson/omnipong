"""OmniPong MCP server.

Exposes the ``omnipong_agent`` actions as Model Context Protocol tools so any
MCP-capable agent can drive omnipong.com on demand — list new area
tournaments, sign up, look up a player, run a full sync, or pull match
history — without knowing Playwright or the site's selectors.

Run (stdio transport, the default for MCP clients):

    .venv/bin/python omnipong_mcp_server.py

Register it with an MCP client, e.g.:

    {
      "mcpServers": {
        "omnipong": {
          "command": "/Users/you/Desktop/omnipong/.venv/bin/python",
          "args": ["/Users/you/Desktop/omnipong/omnipong_mcp_server.py"]
        }
      }
    }

Requires the project's ``.env`` (OMNIPONG_USER / OMNIPONG_PASS) and installed
Playwright Chromium — same prerequisites as the CLI.
"""

from __future__ import annotations

import os as _os

# MCP clients launch stdio servers from an arbitrary working directory, but the
# rest of this project resolves the SQLite DB, browser profile, and .env via
# relative paths. Pin the working directory to the repo root so every client
# behaves identically.
_REPO_ROOT = _os.path.dirname(_os.path.abspath(__file__))
_os.chdir(_REPO_ROOT)

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("omnipong")


def _agent():
    """Import lazily so the server starts without pulling in Playwright."""
    import omnipong_agent

    return omnipong_agent


@mcp.tool()
async def check_new_tournaments(dry_run: bool = False, limit: int | None = None) -> dict:
    """Scan omnipong.com for tournaments in the configured area (default
    Texas / Region 8). By default it creates in-app notifications for
    tournaments not seen before and returns a summary. Set dry_run=True to
    report without writing anything; limit caps how many new ones are handled.
    """
    return await _agent().check(dry_run=dry_run, limit=limit)


@mcp.tool()
async def signup_tournament(title: str, events: list[str] | None = None) -> dict:
    """Register for a tournament by its title as shown on the omnipong list.
    Optionally pass the exact event names to enter; when omitted the agent
    picks events by the user's rating. This performs a REAL registration."""
    return await _agent().signup(title, events)


@mcp.tool()
async def search_player(name: str) -> dict:
    """Look up a player on omnipong.com and return their USATT id, rating, and
    state."""
    return await _agent().search_player(name)


@mcp.tool()
async def list_area_tournaments(deep: bool = False) -> dict:
    """List tournaments currently in the configured area. Set deep=True to also
    scrape each tournament's enterable events (slower)."""
    return await _agent().tournaments(deep=deep)


@mcp.tool()
async def sync_data() -> dict:
    """Run a full crawl: tournaments, leagues, camps, events, details, and the
    user's match history, all into the local database."""
    return await _agent().sync()


@mcp.tool()
async def get_my_matches() -> dict:
    """Scrape the signed-in user's own match history into the local database."""
    return await _agent().matches()


if __name__ == "__main__":
    mcp.run()
