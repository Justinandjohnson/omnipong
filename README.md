# OmniPong — Table Tennis Intelligence Platform

**Tournament data, player ratings, match history, and AI coaching for competitive table tennis.**

[![Live Demo](https://img.shields.io/badge/Live%20Demo-%F0%9F%8F%93%20Try%20Rubberr-blue?style=for-the-badge)](https://omnipong-frontend.onrender.com)
[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/Justinandjohnson/omnipong)

---

## What's in this repo

| App | Description |
|---|---|
| **Rubberr** (`rubberr/`) | AI table tennis coach — match tracking, voice input, analytics |
| **Scorekeeper** (`scorekeeper/`) | iOS live scoring app with SMS notifications |
| **OmniPong scraper** (root) | Player/tournament sync from USATT & Stadium League |

---

## Rubberr — AI Table Tennis Coach

**→ [omnipong-frontend.onrender.com](https://omnipong-frontend.onrender.com)**

### Features

- **Match tracker** — log scores via voice or text, AI parses natural language reports
- **Analytics dashboard** — win rate, rating trend, opponent history, career graph
- **Tournament calendar** — upcoming events synced from USATT & Stadium League
- **Practice partners** — find players near your rating
- **AI coaching chat** — ask anything about your game, tactics, or rubber selection
- **Arcade mode** — quick score entry during live matches

### Try it live

The demo shows a real player's public match history and stats (read-only). To unlock AI coaching features, click **"Add AI Key"** in the banner and enter your own Anthropic or OpenRouter key — stored locally in your browser only.

| Feature | Guest (no key) | Guest + API Key | Admin |
|---|---|---|---|
| View stats & match history | ✓ | ✓ | ✓ |
| Tournament calendar | ✓ | ✓ | ✓ |
| AI coaching chat | — | ✓ | ✓ |
| Voice match input | — | ✓ | ✓ |
| Sync live data | — | — | ✓ |

---

## Run locally

### Prerequisites

- Node.js 20+
- Python 3.11+

### Rubberr frontend

```bash
cd rubberr/frontend
cp .env.local.example .env.local   # set NEXT_PUBLIC_API_URL
npm install
npm run dev
```

Open [http://localhost:3001](http://localhost:3001)

### Rubberr backend (FastAPI)

```bash
cp .env.example .env   # fill in API keys
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r rubberr/backend/requirements.txt  # (or pip install fastapi uvicorn sqlalchemy python-dotenv anthropic openai)
uvicorn rubberr.backend.main:app --reload --port 8000
```

---

## Deploy your own

Click **Deploy to Render** above. The `render.yaml` configures:

- `omnipong-backend` — FastAPI (Python), serves Rubberr API + data sync
- `omnipong-frontend` — Next.js, the Rubberr UI
- `omnipong-db` — PostgreSQL (free tier)

### Required environment variables

```
# Backend
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-proj-...          # Whisper for voice transcription
ELEVENLABS_API_KEY=sk_...           # Voice responses (optional)
DEEPGRAM_API_KEY=...                # Voice transcription alternative (optional)

# Stadium League scraper (optional — needed only for live sync)
STADIUM_USER=your@email.com
STADIUM_PASS=yourpassword
OMNIPONG_USER=your_usatt_username
OMNIPONG_PASS=yourpassword

# Frontend
NEXT_PUBLIC_API_URL=https://your-backend.onrender.com
```

All API keys are optional — the app falls back gracefully. Without keys, match tracking and read-only views still work.

---

## Guest mode — how it works

- The `/demo` backend endpoint returns public player data with no auth required
- Users can enter their own Anthropic/OpenRouter key via the "Add AI Key" banner
- The key is stored in `localStorage` and attached as `X-User-Api-Key` on AI requests
- The backend uses the user key in place of the server key for those requests

---

## Scorekeeper (iOS)

`scorekeeper/` is a SwiftUI app for live score-keeping with SMS notifications via Twilio.

To run: open `scorekeeper/scorekeeper.xcworkspace` in Xcode and run on simulator or device.

To distribute: configure your Twilio credentials in `.env` and submit to TestFlight.

---

## License

Apache License 2.0 — see [LICENSE](LICENSE) and [NOTICE](NOTICE).
Copyright 2026 Justin Johnson.
