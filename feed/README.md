# Tier-2: Always-on public tournament/league feed

Scheduled crawl of omnipong.com's **public** tournament/league listings across
states, normalized into a sanitized dataset, served by a read-only API. This
is Tier 2 of the Rubberr Agent Platform build
(`docs/AGENT_PLATFORM_BUILD_PLAN.md`) and runs on Y6.

Owned exclusively by this directory (`feed/`). It **reads** `omnipong_scraper.py`
and `browser_manager.py` at the repo root but never modifies them.

## What it does

1. `scraper_job.py` logs into omnipong.com with the **owner's** credentials
   (see below), scrapes the public tournament (`e=0`) and league (`e=1`)
   listing pages via `OmniPongScraper.scrape_activities()`, and sanitizes
   every record through `sanitize.py` before writing anything to disk.
2. `sanitize.py` uses an **allowlist**, not a blocklist: only fields on
   `PUBLIC_ACTIVITY_FIELDS` / `PUBLIC_BRACKET_FIELDS` are copied into the
   output record. `contact_name`, `contact_email`, `contact_phone` (and
   anything else not explicitly allowlisted) are dropped by omission, then
   `assert_no_pii()` re-checks every record for banned keys and
   email/phone-shaped substrings in any string value before it is written.
3. `api.py` is a read-only FastAPI app that serves the sanitized dataset as
   JSON — list/filter by state, activity type, or rating bracket, or fetch
   one record by id. **No write endpoints, no auth** — the data is public.

## Why the owner's omnipong.com login is needed

omnipong.com's public listing pages themselves don't require login to view
in a browser, but reliable scraping of the full listing set (and any
per-tournament bracket detail) benefits from an authenticated session using
`browser_manager.login_omnipong()`, which is the existing, already-working
login path. **This is the one place in the whole feed that uses the owner's
own account — and only to read public listing data that any logged-in member
can see.** No other credentials are read, stored, or forwarded anywhere.

Set in the repo-root `.env` (already documented in `.env.example`):

```
OMNIPONG_USER=your_omnipong_username
OMNIPONG_PASS=your_omnipong_password
```

## Running

```bash
# from the repo root
pip install -r requirements.txt -r feed/requirements.txt
playwright install chromium

# one crawl, writes feed/data/tournaments.json, exits 0
python feed/scraper_job.py --once

# or loop forever, one crawl every 6h (default), for hosts with no scheduler
python feed/scraper_job.py

# also pull per-tournament rating brackets (slower: one extra page load
# per listing)
python feed/scraper_job.py --once --include-brackets

# serve the read-only API
uvicorn feed.api:app --host 0.0.0.0 --port 8090
```

### Scheduling on Y6 (Windows)

No scheduler dependency is used — `scraper_job.py --once` is a plain,
cron-friendly entrypoint. On Y6, register it with **Task Scheduler**:

```
Program:   C:\path\to\venv\Scripts\python.exe
Arguments: feed\scraper_job.py --once
Start in:  C:\path\to\omnipong
Trigger:   Daily, repeat every 6 hours (or whatever cadence is desired)
```

Equivalent on a cron-capable host:

```
0 */6 * * * cd /path/to/omnipong && ./venv/bin/python feed/scraper_job.py --once
```

The built-in loop mode (`python feed/scraper_job.py`, no `--once`) is a
fallback for hosts without an OS scheduler — it is the same `run_once()`
call, just wrapped in a `time.sleep()` loop, and one failed cycle logs and
retries next interval instead of crashing the process.

## API

```
GET /health
GET /tournaments?state=TX&activity_type=tournament&min_rating=1800&limit=50&offset=0
GET /tournaments/{id}
```

`FEED_DATA_PATH` env var overrides the dataset path (default
`feed/data/tournaments.json`); useful for pointing the API at a fixture in
tests. If the dataset file doesn't exist yet, `/tournaments` and
`/tournaments/{id}` return a clean `503` (not a silent empty list) telling
the caller to run `scraper_job.py --once` first — no fallback data source.

## Sanitization guarantee

Every record served by this API has:

- **No** `contact_name`, `contact_email`, or `contact_phone` key (allowlist —
  these were never copied in the first place).
- **No** email-shaped (`x@y.z`) or US-phone-shaped substring in any field
  value, verified by regex in `assert_no_pii()`, run on every record at
  write time (`scraper_job.py`) — a scraper bug that adds a new PII-bearing
  field cannot silently ship, because it isn't on the allowlist and would
  additionally trip the regex check if the value happened to be, say, an
  email embedded in a free-text field.
- Only public listing fields: `id`, `title`, `date_range`, `activity_type`,
  `status`, `url`, `city`, `state`, and optional `brackets` (`name`, `fee`,
  `rating_limit`, `start_time`, `status` — no PII in bracket data either).

## Self-check / test

```bash
python feed/test_sanitizer.py
```

Proves, with a realistic fixture record (title/dates/city/state plus a fake
`contact_name`/`contact_email`/`contact_phone`, exactly as
`OmniPongScraper.scrape_activities()` would emit it):

1. `sanitize_activity()` strips all PII keys and any email/phone-shaped
   value, recursively, while keeping the public fields intact and correctly
   parsed (e.g. `"Austin, TX"` → `city="Austin"`, `state="TX"`).
2. `sanitize_activity()` fails loudly (`ValueError`) on a malformed record
   (missing `source_id`) instead of silently publishing a broken one.
3. The read-only API, pointed at a fixture dataset built from that sanitized
   sample, returns `/health`, `/tournaments`, `/tournaments/{id}` correctly,
   the raw HTTP response bodies contain **no** PII substrings, and the
   `state`/`min_rating`/`max_rating` filters work.
4. The API returns a clean `503` (not empty JSON) when no dataset file
   exists yet.

No live network calls, no owner login required to run this test — it is a
pure fixture-based check, per the instruction not to run a live scrape
against omnipong.com in this task.

## What still needs the owner's login to fully verify

This test suite proves the sanitizer and API are correct against a
realistic fixture. It does **not** prove:

- That `scraper_job.py --once` actually logs into omnipong.com successfully
  and that `scrape_activities()`'s real output still matches the field
  names `sanitize_activity()` expects (the scraper's HTML-table heuristics
  could drift if omnipong.com's markup changes).
- Real-world timing/volume: how many tournament/league records a real crawl
  returns, and how long it takes.
- That `--include-brackets` correctly navigates to each tournament's entry
  page in bulk without tripping rate limits or bot detection on
  omnipong.com.

To verify those, run `python feed/scraper_job.py --once` with
`OMNIPONG_USER`/`OMNIPONG_PASS` set in the repo-root `.env`, then inspect
`feed/data/tournaments.json` and re-run `python feed/test_sanitizer.py`'s
`assert_no_pii` logic against the real output if desired.
