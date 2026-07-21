"""Self-check: sanitizer strips PII from a realistic raw record, and the
read-only API serves that sanitized sample correctly.

Run directly (no live scrape, no owner login needed):
    python feed/test_sanitizer.py
or via pytest:
    pytest feed/test_sanitizer.py -v
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

FEED_DIR = Path(__file__).resolve().parent
REPO_ROOT = FEED_DIR.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from feed.sanitize import assert_no_pii, sanitize_activity  # noqa: E402

# A realistic raw record exactly as OmniPongScraper.scrape_activities() emits it
# (see omnipong_scraper.py scrape_activities()), including the PII fields it
# extracts from the contact column.
SAMPLE_RAW_ACTIVITY = {
    "source": "omnipong",
    "source_id": "T-tourney.asp?r=123456",
    "title": "Spring Open Table Tennis Championship",
    "location": "Austin, TX",
    "city_state": "Austin, TX",
    "date_range": "08/15/26 - 08/16/26",
    "activity_type": "tournament",
    "status": "upcoming",
    "url": "https://www.omnipong.com/t-tourney.asp?e=0",
    "contact_name": "Jane Organizer",
    "contact_email": "jane.organizer@example.com",
    "contact_phone": "(512) 555-0199",
}

SAMPLE_RAW_BRACKETS = [
    {"name": "Open Singles", "fee": 35.0, "rating_limit": 0, "start_time": "9:00 AM", "status": "Open"},
    {"name": "Under 1800", "fee": 25.0, "rating_limit": 1800, "start_time": "1:00 PM", "status": "Open"},
]


def test_sanitize_strips_all_pii() -> None:
    raw = {**SAMPLE_RAW_ACTIVITY, "brackets": SAMPLE_RAW_BRACKETS}
    clean = sanitize_activity(raw)

    # 1. Banned keys must be gone entirely.
    for banned in ("contact_name", "contact_email", "contact_phone", "raw_details"):
        assert banned not in clean, f"{banned} leaked into sanitized record"

    # 2. No email/phone-shaped substring anywhere in any value, recursively.
    def _walk(value):
        if isinstance(value, dict):
            assert_no_pii(value)
            for v in value.values():
                _walk(v)
        elif isinstance(value, list):
            for v in value:
                _walk(v)

    _walk(clean)
    assert_no_pii(clean)  # top-level guarantee, same check the job/API rely on

    # 3. Public fields survived and are correct.
    assert clean["title"] == "Spring Open Table Tennis Championship"
    assert clean["city"] == "Austin"
    assert clean["state"] == "TX"
    assert clean["activity_type"] == "tournament"
    assert clean["status"] == "upcoming"
    assert clean["id"] == "omnipong_123456"
    assert len(clean["brackets"]) == 2
    assert clean["brackets"][1]["rating_limit"] == 1800

    print("OK: sanitize_activity() strips all PII, keeps public fields.")
    return clean


def test_sanitize_requires_source_id() -> None:
    bad = {**SAMPLE_RAW_ACTIVITY, "source_id": ""}
    try:
        sanitize_activity(bad)
    except ValueError:
        print("OK: sanitize_activity() fails loudly on missing source_id (no silent fallback).")
        return
    raise AssertionError("sanitize_activity() should have raised ValueError on empty source_id")


def test_api_serves_sanitized_sample(tmp_data_path: Path | None = None) -> None:
    import os
    import tempfile

    from fastapi.testclient import TestClient

    clean_sample = sanitize_activity({**SAMPLE_RAW_ACTIVITY, "brackets": SAMPLE_RAW_BRACKETS})

    fd, path_str = tempfile.mkstemp(suffix=".json")
    path = Path(path_str)
    try:
        with os.fdopen(fd, "w") as f:
            json.dump({"generated_at": "2026-07-20T00:00:00+00:00", "count": 1, "records": [clean_sample]}, f)

        os.environ["FEED_DATA_PATH"] = str(path)

        from feed.api import app

        client = TestClient(app)

        resp = client.get("/health")
        assert resp.status_code == 200 and resp.json() == {"status": "ok"}

        resp = client.get("/tournaments")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        assert body["records"][0]["id"] == clean_sample["id"]
        raw_body = resp.text
        assert "jane.organizer@example.com" not in raw_body
        assert "555-0199" not in raw_body
        assert "contact_" not in raw_body

        resp = client.get(f"/tournaments/{clean_sample['id']}")
        assert resp.status_code == 200
        assert resp.json() == clean_sample

        resp = client.get("/tournaments/does-not-exist")
        assert resp.status_code == 404

        resp = client.get("/tournaments", params={"state": "TX"})
        assert resp.json()["total"] == 1
        resp = client.get("/tournaments", params={"state": "CA"})
        assert resp.json()["total"] == 0

        resp = client.get("/tournaments", params={"min_rating": 1800})
        assert resp.json()["total"] == 1
        resp = client.get("/tournaments", params={"min_rating": 5000})
        assert resp.json()["total"] == 0

        print("OK: read-only API serves the sanitized sample, no PII in any response, filters work.")
    finally:
        os.environ.pop("FEED_DATA_PATH", None)
        path.unlink(missing_ok=True)


def test_api_clean_error_when_no_data() -> None:
    import os

    from fastapi.testclient import TestClient

    os.environ["FEED_DATA_PATH"] = "/tmp/does-not-exist-omnipong-feed.json"
    try:
        from feed.api import app

        client = TestClient(app)
        resp = client.get("/tournaments")
        assert resp.status_code == 503
        assert "not generated yet" in resp.json()["detail"]
        print("OK: API fails loudly (503) instead of silently serving an empty feed when data is missing.")
    finally:
        os.environ.pop("FEED_DATA_PATH", None)


if __name__ == "__main__":
    test_sanitize_strips_all_pii()
    test_sanitize_requires_source_id()
    test_api_serves_sanitized_sample()
    test_api_clean_error_when_no_data()
    print("\nAll feed self-checks passed.")
