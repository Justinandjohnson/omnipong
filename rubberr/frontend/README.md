# Rubberr — AI Table Tennis Coach (Frontend)

Next.js 15 frontend for the Rubberr table tennis intelligence platform.

**→ [omnipong-frontend.onrender.com](https://omnipong-frontend.onrender.com)**

See the [root README](../../README.md) for full project docs, deployment instructions, and the backend setup.

## Quick start

```bash
npm install
cp .env.local.example .env.local    # set NEXT_PUBLIC_API_URL=http://localhost:8000
npm run dev
```

Open [http://localhost:3001](http://localhost:3001)

## Pages

| Route | Description |
|---|---|
| `/` | Dashboard — stats, career graph, recent matches |
| `/analytics` | Deep analytics — pattern analysis, opponent breakdown |
| `/tournaments` | Upcoming events from USATT + Stadium League |
| `/scoreboard` | Live arcade scoring mode |
| `/chat` | AI coaching chat |
| `/map` | Practice partners map |
| `/settings` | App settings + API key management |
