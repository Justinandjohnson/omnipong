# ops — scheduling the OmniPong agent

## Daily tournament scout (macOS launchd)

`daily_check.py` should run once a day. This directory ships a launchd
installer so that happens automatically on this Mac.

```bash
# Install (daily at 09:00 by default)
ops/install_daily_check.sh

# Choose a different time
DAILY_CHECK_HOUR=7 DAILY_CHECK_MINUTE=30 ops/install_daily_check.sh

# Run it immediately, once
launchctl kickstart -k gui/$(id -u)/com.omnipong.dailycheck

# Check status
launchctl list | grep omnipong

# Remove
ops/uninstall_daily_check.sh
```

Logs land in `logs/daily_check.out.log` and `logs/daily_check.err.log`
(both git-ignored).

### What it does each day

1. Logs into omnipong.com with `OMNIPONG_USER` / `OMNIPONG_PASS`.
2. Scans tournaments and keeps the local DB current for the configured area
   (`AREA_REGION`, `AREA_CITIES` — defaults to Texas / Region 8).
3. For every tournament **not alerted before**, deep-scrapes its events,
   builds an AI recommendation, and writes an in-app `Notification`.
4. The Rubberr dashboard's `AIAlertPopup` shows it and offers
   **"Sign Up with AI"** → `POST /tournaments/signup` → real registration.

### Requirements

- `.venv` with `requirements.txt` installed and Playwright Chromium present
  (`playwright install chromium`).
- A `.env` at the repo root with `OMNIPONG_USER` / `OMNIPONG_PASS`.
- The Mac awake at the scheduled time (launchd does not wake a sleeping Mac
  for a missed `StartCalendarInterval` until next login; if the Mac was
  asleep, the run happens at the next wake).

### On other hosts

`daily_check.py` is a plain script, so any scheduler works — cron
(`0 9 * * * cd /path/to/omnipong && .venv/bin/python daily_check.py`) or a
Windows Task Scheduler entry. See also `feed/scraper_job.py`, which has its
own `--once` / self-loop modes for the public feed.
