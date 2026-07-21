"""Tier-2 scheduled job: crawl omnipong.com public tournament/league listings,
sanitize them, and write the public dataset feed/api.py serves.

Reuses OmniPongScraper + BrowserManager from the repo root (imported, never
modified — see docs/AGENT_PLATFORM_BUILD_PLAN.md Agent D file ownership).

Auth: the scraper logs into omnipong.com using the OWNER's own credentials
(OMNIPONG_USER / OMNIPONG_PASS, read by browser_manager._get_cred from the
repo root .env or .credentials.json). This is the one place owner creds are
used in this feed, and it is only ever used to read PUBLIC tournament/league
listings — no private data is scraped or stored here.

Schedule mechanism: no scheduler dependency. Two ways to run this file:
  1. `python scraper_job.py --once`      -> single crawl + exit, 0 on success.
     Point a cron / Windows Task Scheduler entry at this for production.
  2. `python scraper_job.py`             -> loops forever, one crawl per
     --interval-seconds (default 6h), for hosts with no external scheduler.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path

FEED_DIR = Path(__file__).resolve().parent
REPO_ROOT = FEED_DIR.parent
DEFAULT_OUT = FEED_DIR / "data" / "tournaments.json"

# omnipong_scraper.py / browser_manager.py live at the repo root and use bare
# `import browser_manager` / `from models import ...` — they are only
# importable if the repo root is on sys.path.
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from feed.sanitize import sanitize_activity  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("feed.scraper_job")

# Tier-2 is tournaments (0) and leagues (1) only. Camps (2) are out of scope
# for the public tournament/league feed per the build plan.
ACTIVITY_TYPE_IDS = (0, 1)


def _strip_domain(source_id: str) -> str:
    for prefix in ("https://www.omnipong.com/", "http://www.omnipong.com/"):
        if source_id.startswith(prefix):
            return source_id[len(prefix):]
    return source_id.lstrip("/")


async def crawl_public_feed(*, include_brackets: bool = False) -> list[dict]:
    """Log in with the owner's omnipong.com account and scrape PUBLIC listings only.

    Returns sanitized records — raw contact_name/email/phone never leaves
    this function (sanitize_activity() strips it via allowlist + asserts).
    """
    # Imported lazily so importing this module (e.g. from tests) doesn't
    # require playwright/sqlalchemy to be installed unless a crawl runs.
    from browser_manager import BrowserManager
    from omnipong_scraper import OmniPongScraper

    manager = BrowserManager()
    scraper = OmniPongScraper(manager)
    records: list[dict] = []
    try:
        ok = await manager.login_omnipong()
        if not ok:
            raise RuntimeError(
                "OmniPong login failed; check OMNIPONG_USER/OMNIPONG_PASS "
                "(owner credentials, .env or .credentials.json)"
            )

        for type_id in ACTIVITY_TYPE_IDS:
            raw_activities = await scraper.scrape_activities(type_id)
            log.info("type_id=%s: scraped %d raw activities", type_id, len(raw_activities))

            for raw in raw_activities:
                if include_brackets:
                    clean_sid = _strip_domain(raw["source_id"])
                    try:
                        raw = {**raw, "brackets": await scraper.scrape_activity_events(clean_sid)}
                    except Exception as exc:  # noqa: BLE001 - one bad bracket page must not kill the crawl
                        log.warning("bracket scrape failed for %s: %s", raw.get("title"), exc)

                records.append(sanitize_activity(raw))

        return records
    finally:
        await manager.stop()


def write_feed(records: list[dict], out_path: Path = DEFAULT_OUT) -> None:
    """Atomic write: tmp file + os.replace, so readers never see a partial file."""
    payload = {
        "generated_at": datetime.now(UTC).isoformat(),
        "count": len(records),
        "records": records,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=out_path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(payload, f, indent=2)
        os.replace(tmp_path, out_path)
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


async def run_once(*, include_brackets: bool = False, out_path: Path = DEFAULT_OUT) -> int:
    records = await crawl_public_feed(include_brackets=include_brackets)
    write_feed(records, out_path)
    log.info("wrote %d sanitized records to %s", len(records), out_path)
    return len(records)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true", help="Run a single crawl and exit (cron mode).")
    parser.add_argument(
        "--interval-seconds",
        type=int,
        default=6 * 3600,
        help="Loop interval when not using --once (default 6h).",
    )
    parser.add_argument(
        "--include-brackets",
        action="store_true",
        help="Also scrape per-tournament event/rating brackets (slower — one extra page load per listing).",
    )
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="Output JSON path.")
    args = parser.parse_args()

    if args.once:
        count = asyncio.run(run_once(include_brackets=args.include_brackets, out_path=args.out))
        sys.exit(0 if count >= 0 else 1)

    log.info("looping every %ds (Ctrl+C to stop)", args.interval_seconds)
    while True:
        try:
            asyncio.run(run_once(include_brackets=args.include_brackets, out_path=args.out))
        except Exception:  # noqa: BLE001 - one failed cycle must not kill the scheduled loop
            log.exception("crawl cycle failed; will retry next interval")
        time.sleep(args.interval_seconds)


if __name__ == "__main__":
    main()
