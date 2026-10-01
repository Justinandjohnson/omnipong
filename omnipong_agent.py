"""OmniPong Agent — one clean surface for every omnipong.com action.

This is the "do anything we ask, any time" entry point. It wraps the existing
pieces (``browser_manager.BrowserManager`` + ``omnipong_scraper.OmniPongScraper``
+ the daily scout) behind a small set of named actions, exposed both as a CLI:

    python omnipong_agent.py check                 # daily scout (new-only alerts)
    python omnipong_agent.py check --dry-run       # scout without writing alerts
    python omnipong_agent.py signup --title "..."  # register for a tournament
    python omnipong_agent.py search --name "..."   # player rating / USATT lookup
    python omnipong_agent.py sync                  # full crawl into the DB
    python omnipong_agent.py matches               # my match history
    python omnipong_agent.py tournaments           # tournaments in my area

...and as an importable async API (``run_action``), which is what the MCP
server (``omnipong_mcp_server.py``) calls. Nothing here hard-codes personal
data — area/identity come from the environment (see ``omnipong_config.py``).
"""

from __future__ import annotations

import argparse
import asyncio
import json
from typing import Any

from browser_manager import BrowserManager
from omnipong_config import area_cities, area_region
from omnipong_scraper import OmniPongScraper, init_db

# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------


async def check(*, dry_run: bool = False, deep: bool = True, limit: int | None = None) -> dict:
    """Daily scout: alert on new area tournaments (see ``daily_check.py``)."""
    from daily_check import daily_check

    return await daily_check(deep=deep, notify=not dry_run, limit=limit)


async def signup(title: str, events: list[str] | None = None) -> dict:
    """Register for a tournament by title, optionally naming its events."""
    if not title or not title.strip():
        return {"status": "error", "message": "tournament title is required"}

    manager = BrowserManager()
    scraper = OmniPongScraper(manager)
    try:
        ok = await manager.login_omnipong()
        if not ok:
            return {"status": "error", "message": "OmniPong login failed"}
        return await scraper.signup_for_tournament(title.strip(), events)
    finally:
        await manager.stop()


async def search_player(name: str) -> dict:
    """Look up a player's USATT id / rating / state on OmniPong."""
    if not name or not name.strip():
        return {"status": "error", "message": "player name is required"}

    manager = BrowserManager()
    try:
        return await manager.search_omnipong_player(name.strip())
    finally:
        await manager.stop()


async def sync() -> dict:
    """Full crawl (tournaments, leagues, camps, events, details, matches)."""
    import autoscrape

    await autoscrape.main()
    return {"status": "success", "message": "full sync complete"}


async def matches() -> dict:
    """Scrape my own match history into the DB."""
    manager = BrowserManager()
    scraper = OmniPongScraper(manager)
    try:
        ok = await manager.login_omnipong()
        if not ok:
            return {"status": "error", "message": "OmniPong login failed"}
        rows = await scraper.scrape_my_matches()
        return {"status": "success", "matches": rows}
    finally:
        await manager.stop()


async def tournaments(*, deep: bool = False) -> dict:
    """List tournaments currently in the configured area.

    ``deep`` also scrapes each tournament's events (slower).
    """
    from omnipong_config import activity_in_area

    await init_db()
    manager = BrowserManager()
    scraper = OmniPongScraper(manager)
    try:
        ok = await manager.login_omnipong()
        if not ok:
            return {"status": "error", "message": "OmniPong login failed"}
        activities = await scraper.scrape_activities(0) or []
        area = [a for a in activities if activity_in_area(a)]

        # Insert/update the listing first (no 'events' key) so that the
        # deep-scrape below always upserts existing rows rather than trying to
        # insert a brand-new Activity with a non-column 'events' key.
        if area:
            await scraper.save_activities(area)

        if deep:
            for a in area:
                try:
                    a["events"] = await scraper.scrape_activity_events(a["source_id"])
                except Exception:  # noqa: BLE001 - one bad page must not stop the pass
                    a["events"] = []
                # PDF entry form: keep the URL as the flyer and the extracted
                # text as raw_details so the agent can read the form.
                form = getattr(scraper, "last_entry_form", None)
                scraper.last_entry_form = None
                if form:
                    if form.get("url"):
                        a["flyer_url"] = form["url"]
                    if form.get("text"):
                        a["raw_details"] = form["text"]
            await scraper.save_activities(area)
        return {
            "status": "success",
            "region": area_region(),
            "cities": list(area_cities()),
            "count": len(area),
            "tournaments": area,
        }
    finally:
        await manager.stop()


ACTION_MAP = {
    "check": check,
    "signup": signup,
    "search": search_player,
    "sync": sync,
    "matches": matches,
    "tournaments": tournaments,
}


async def run_action(action: str, **kwargs: Any) -> dict:
    """Programmatic entry point used by the MCP server."""
    func = ACTION_MAP.get(action)
    if func is None:
        return {"status": "error", "message": f"unknown action: {action!r}"}
    return await func(**kwargs)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="action", required=True)

    p_check = sub.add_parser("check", help="Daily scout for new area tournaments.")
    p_check.add_argument("--dry-run", action="store_true", help="Report only; write no notifications.")
    p_check.add_argument("--no-deep", action="store_true", help="Skip per-tournament event scrape.")
    p_check.add_argument("--limit", type=int, default=None, help="Cap new tournaments processed.")

    p_signup = sub.add_parser("signup", help="Register for a tournament.")
    p_signup.add_argument("--title", required=True, help="Tournament title (as shown on the list).")
    p_signup.add_argument("--event", action="append", dest="events", default=None, help="Event name (repeatable).")

    p_search = sub.add_parser("search", help="Look up a player.")
    p_search.add_argument("--name", required=True)

    sub.add_parser("sync", help="Full crawl into the local DB.")

    sub.add_parser("matches", help="Scrape my match history.")

    p_tour = sub.add_parser("tournaments", help="List area tournaments.")
    p_tour.add_argument("--deep", action="store_true", help="Also scrape each tournament's events.")

    return parser


def main() -> None:
    args = _build_parser().parse_args()
    action = args.action

    if action == "check":
        coro = check(dry_run=args.dry_run, deep=not args.no_deep, limit=args.limit)
    elif action == "signup":
        coro = signup(args.title, args.events)
    elif action == "search":
        coro = search_player(args.name)
    elif action == "tournaments":
        coro = tournaments(deep=args.deep)
    else:
        coro = ACTION_MAP[action]()

    print(json.dumps(asyncio.run(coro), indent=2, default=str))


if __name__ == "__main__":
    main()
