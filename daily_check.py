"""Daily OmniPong tournament scout.

Once a day this logs into omnipong.com, scans the tournament listing, keeps
the local DB current for the configured area (default: Texas / Region 8 — see
``omnipong_config.py``), and raises an in-app ``Notification`` for every
tournament in the area the user has **not been notified about before**.

A notification carries everything the frontend ``AIAlertPopup`` needs to ask
"sign me up?" and, on a yes, drive ``OmniPongScraper.signup_for_tournament``
via ``POST /tournaments/signup`` — so the whole loop is:
scout -> in-app alert -> user clicks "Sign Up with AI" -> registered.

Design notes:
- Only *new* tournaments get the expensive treatment (deep event scrape +
  AI recommendation). Already-notified ones are skipped, which keeps the
  daily run fast and the alerts meaningful.
- "New" means "no existing ``new_tournament`` notification for this title",
  which makes the scout idempotent: re-running it never re-alerts.
- No email/SMS is sent (the project chose in-app only); the notification row
  is the delivery channel.

Run it directly (``python daily_check.py``) or via the scheduler — see
``ops/`` for the launchd installer.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from typing import Any

from sqlalchemy import select

from browser_manager import BrowserManager
from models import Notification
from omnipong_config import activity_in_area, area_cities, area_region
from omnipong_scraper import AsyncSessionLocal, OmniPongScraper, init_db

# tournament_intelligence lives in the backend package and uses bare imports.
_BACKEND_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "rubberr", "backend")
)
if _BACKEND_DIR not in sys.path:
    sys.path.append(_BACKEND_DIR)

NOTIFICATION_TYPE = "new_tournament"
TOURNAMENT_TYPE_ID = 0  # scrape_activities(0) == Tournaments


async def _notified_titles() -> set[str]:
    """Titles we have already raised a ``new_tournament`` alert for."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Notification).where(Notification.type == NOTIFICATION_TYPE)
        )
        titles: set[str] = set()
        for notif in result.scalars().all():
            try:
                content = (
                    json.loads(notif.content)
                    if isinstance(notif.content, str)
                    else notif.content
                )
            except (TypeError, ValueError):
                continue
            title = (content or {}).get("title")
            if title:
                titles.add(title)
        return titles


def _recommendation_for(title: str) -> dict:
    """AI event recommendation for a tournament, or a safe empty shape.

    The frontend reads ``content.recommendation.recommended_events``; when the
    intelligence layer has nothing, an empty list is correct — the signup
    endpoint then falls back to ``SmartEventMatcher``.
    """
    from tournament_intelligence import get_tournament_intelligence

    intel = get_tournament_intelligence(title) or {}
    recommendations = intel.get("recommendations") or []
    if recommendations:
        return recommendations[0]
    return {"tournament": title, "recommended_events": []}


async def _create_notification(activity: dict, recommendation: dict) -> int:
    content = json.dumps(
        {
            "title": activity["title"],
            "date": activity.get("date_range"),
            "location": activity.get("city_state") or activity.get("location"),
            "source_id": activity.get("source_id"),
            "url": activity.get("url"),
            "recommendation": recommendation,
        }
    )
    async with AsyncSessionLocal() as session:
        notif = Notification(type=NOTIFICATION_TYPE, content=content, is_read=False)
        session.add(notif)
        await session.commit()
        return notif.id


async def daily_check(
    *,
    deep: bool = True,
    notify: bool = True,
    limit: int | None = None,
) -> dict[str, Any]:
    """Run one scout pass.

    Args:
        deep: deep-scrape event brackets for new tournaments (needed for good
            AI recommendations). Set ``False`` for a fast listing-only pass.
        notify: create ``Notification`` rows. ``False`` = dry run.
        limit: cap how many new tournaments get the full treatment.

    Returns a JSON-serialisable summary.
    """
    await init_db()

    manager = BrowserManager()
    scraper = OmniPongScraper(manager)
    summary: dict[str, Any] = {
        "region": area_region(),
        "cities": list(area_cities()),
        "scanned": 0,
        "in_area": 0,
        "new": 0,
        "skipped_existing": 0,
        "notified": [],
        "dry_run": not notify,
    }

    try:
        ok = await manager.login_omnipong()
        if not ok:
            raise RuntimeError(
                "OmniPong login failed — check OMNIPONG_USER / OMNIPONG_PASS."
            )

        activities = await scraper.scrape_activities(TOURNAMENT_TYPE_ID) or []
        summary["scanned"] = len(activities)

        area = [a for a in activities if activity_in_area(a)]
        summary["in_area"] = len(area)

        # Keep the local DB current for the whole area (cheap: listing only).
        if area:
            await scraper.save_activities(area)

        already_notified = await _notified_titles()
        new = [a for a in area if a.get("title") and a["title"] not in already_notified]
        summary["skipped_existing"] = len(area) - len(new)
        if limit is not None:
            new = new[:limit]
        summary["new"] = len(new)

        for activity in new:
            print(f"[daily_check] NEW in area: {activity['title']}")

            if deep:
                try:
                    activity["events"] = await scraper.scrape_activity_events(
                        activity["source_id"]
                    )
                except Exception as exc:  # noqa: BLE001 - one bad page must not stop the pass
                    print(f"[daily_check] event scrape failed for {activity['title']}: {exc}")
                    activity["events"] = []
                # The activity already exists from the area save above, so this
                # upserts and attaches its events.
                await scraper.save_activities([activity])

            if notify:
                recommendation = _recommendation_for(activity["title"])
                notif_id = await _create_notification(activity, recommendation)
                summary["notified"].append(
                    {"title": activity["title"], "notification_id": notif_id}
                )

        return summary
    finally:
        await manager.stop()


def main() -> None:
    print(json.dumps(asyncio.run(daily_check()), indent=2, default=str))


if __name__ == "__main__":
    main()
