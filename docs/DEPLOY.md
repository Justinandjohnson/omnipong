# Deployment (Cloudflare)

Both demos are hosted on Cloudflare. There is exactly one method per piece — no
fallbacks. If a dependency is missing the code errors cleanly rather than
silently degrading.

## Live URLs

| Piece | URL | What it is |
|-------|-----|------------|
| Rubberr demo | https://rubberr.pages.dev | Static stats/matches (baked seed JSON) + live BYOK coaching chat |
| Rubberr chat Worker | https://rubberr-chat.justinandjohnson.workers.dev | BYOK proxy to the Anthropic API (key supplied per-request, never stored) |
| OmniPong demo | https://omnipong-demo.pages.dev | Sanitized tournament list + client-side rule-based `SmartEventMatcher` |

## Layout

```
demos/rubberr/     index.html + data.json   -> Cloudflare Pages project "rubberr"
demos/omnipong/    index.html + data.json   -> Cloudflare Pages project "omnipong-demo"
workers/rubberr-chat/  src/index.js + wrangler.toml -> Worker "rubberr-chat"
```

## Deploy commands

```bash
# Chat Worker
cd workers/rubberr-chat && npx wrangler deploy

# Pages (create project once, then deploy)
npx wrangler pages deploy demos/rubberr        --project-name rubberr        --branch main
npx wrangler pages deploy demos/omnipong       --project-name omnipong-demo  --branch main
```

## Regenerating the demo data

- **Rubberr** (`demos/rubberr/data.json`): seed a SQLite DB with
  `rubberr/backend/seed.py`, then run the `/demo` query. The showcase identity is
  configurable via `PLAYER_FULL_NAME` / `PLAYER_EMAIL` (generic by default).
- **OmniPong** (`demos/omnipong/data.json`): a sanitized subset exported from
  `omnipong.db`. Contact names, emails, and phone numbers are stripped — only
  public tournament listing fields and the rating-bracket event menu remain.

## What does NOT run on Cloudflare

Live tournament scraping uses **Playwright** (a headless browser) and therefore
**cannot run on Cloudflare Workers/Pages**. It stays a local / external job:

- `autoscrape.py`, `daily_check.py`, `omnipong_scraper.py`, and the Stadium
  scrapers under `rubberr/backend/` require a real browser and a logged-in
  session on the third-party sites.
- Run them locally or on a scheduled box (e.g. GitHub Actions cron / a small VM)
  that writes results into the database.
- The hosted demos are **read-only** and serve committed, sanitized data. They
  never scrape live and never touch third-party logins.

## Honest framing

OmniPong is a **tournament scraper + rule-based event matcher** (regex on rating
brackets), not an AI agent. The demo is labeled accordingly.
