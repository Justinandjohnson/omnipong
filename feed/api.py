"""Tier-2 read-only public API: serves the sanitized omnipong.com tournament/
league feed as JSON. No write endpoints, no auth (the underlying data is
public) — see docs/AGENT_PLATFORM_BUILD_PLAN.md.

Run: `uvicorn feed.api:app --host 0.0.0.0 --port 8090` from the repo root.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query

FEED_DIR = Path(__file__).resolve().parent
DEFAULT_DATA_PATH = FEED_DIR / "data" / "tournaments.json"

app = FastAPI(
    title="OmniPong Public Tournament Feed",
    description="Read-only, sanitized public tournament/league listings (Tier 2).",
    version="1.0.0",
)


def _data_path() -> Path:
    # Read the env var on every call (not cached at import time) so tests can
    # point the API at a fixture file without re-importing the module.
    return Path(os.environ.get("FEED_DATA_PATH", str(DEFAULT_DATA_PATH)))


def _load_dataset() -> dict:
    path = _data_path()
    if not path.exists():
        raise HTTPException(
            status_code=503,
            detail=f"feed data not generated yet: {path} does not exist. Run scraper_job.py --once first.",
        )
    with path.open() as f:
        return json.load(f)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/tournaments")
def list_tournaments(
    state: str | None = Query(None, description="Two-letter state filter, e.g. TX"),
    activity_type: str | None = Query(None, description="tournament | league"),
    min_rating: int | None = Query(None, description="Only include listings with a bracket rating_limit >= this"),
    max_rating: int | None = Query(None, description="Only include listings with a bracket rating_limit <= this"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> dict:
    dataset = _load_dataset()
    records = dataset["records"]

    if state:
        records = [r for r in records if (r.get("state") or "").upper() == state.upper()]
    if activity_type:
        records = [r for r in records if r.get("activity_type") == activity_type]
    if min_rating is not None:
        records = [
            r for r in records
            if any(b.get("rating_limit", 0) >= min_rating for b in r.get("brackets", []))
        ]
    if max_rating is not None:
        records = [
            r for r in records
            if any(0 < b.get("rating_limit", 0) <= max_rating for b in r.get("brackets", []))
        ]

    total = len(records)
    page = records[offset : offset + limit]
    return {
        "generated_at": dataset.get("generated_at"),
        "total": total,
        "limit": limit,
        "offset": offset,
        "records": page,
    }


@app.get("/tournaments/{tournament_id}")
def get_tournament(tournament_id: str) -> dict:
    dataset = _load_dataset()
    for record in dataset["records"]:
        if record.get("id") == tournament_id:
            return record
    raise HTTPException(status_code=404, detail=f"no tournament with id {tournament_id!r}")
