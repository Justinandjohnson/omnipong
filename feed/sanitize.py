"""Sanitize raw OmniPong scrape output into the public, PII-free feed schema.

One method, no fallback chain: `sanitize_activity()` is the only entry point.
It uses an ALLOWLIST (not a blocklist) of output fields, so a new PII field
added to the scraper later cannot silently leak through — it would simply be
dropped unless explicitly added to `PUBLIC_ACTIVITY_FIELDS` below.

`assert_no_pii()` is the self-check every caller (job + tests) runs against
every record before it is ever written to disk or served over the API.
"""

from __future__ import annotations

import re

# Fields from OmniPongScraper.scrape_activities()/_extract_tournament_list_from_table()
# that are safe to publish. Everything else (contact_name, contact_email,
# contact_phone, raw_details, flyer_url, etc.) is dropped by omission.
PUBLIC_ACTIVITY_FIELDS = {
    "title",
    "date_range",
    "activity_type",
    "status",
    "url",
}

# Bracket/event fields (from scrape_activity_events()) are already PII-free
# (name, fee, rating_limit, start_time, status) but we allowlist them too,
# for the same reason.
PUBLIC_BRACKET_FIELDS = {
    "name",
    "fee",
    "rating_limit",
    "start_time",
    "status",
}

_ID_RE = re.compile(r"[rht]?-?tourney\.asp\?[rht]=(\d+)", re.IGNORECASE)
_ID_FALLBACK_RE = re.compile(r"[?&][rht]=(\d+)", re.IGNORECASE)
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w.-]+\.\w+")
_PHONE_RE = re.compile(r"(?:\+?1[\s.-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}")

# Banned key names — belt-and-suspenders on top of the allowlist. If any of
# these ever show up as a key in a sanitized record, sanitize_activity() has
# a bug and must fail loudly rather than publish.
_BANNED_KEYS = {"contact_name", "contact_email", "contact_phone", "raw_details"}


def _derive_id(source: str, source_id: str) -> str:
    """Stable public id derived from the tournament/league id param, never the raw URL."""
    if not source_id:
        raise ValueError("activity missing source_id; cannot derive public id")
    m = _ID_RE.search(source_id) or _ID_FALLBACK_RE.search(source_id)
    suffix = m.group(1) if m else re.sub(r"\W+", "_", source_id.strip("/"))
    return f"{source}_{suffix}"


def _split_city_state(location: str | None) -> tuple[str | None, str | None]:
    if not location:
        return None, None
    parts = [p.strip() for p in location.split(",") if p.strip()]
    if len(parts) >= 2:
        return parts[0], parts[-1]
    return parts[0] if parts else None, None


def sanitize_bracket(raw_bracket: dict) -> dict:
    return {k: raw_bracket[k] for k in PUBLIC_BRACKET_FIELDS if k in raw_bracket}


def sanitize_activity(raw: dict) -> dict:
    """Turn one raw scraped activity dict into the public, sanitized record.

    Raises on missing required fields rather than silently substituting
    defaults — a malformed scrape must fail loudly, not publish a half-empty
    or wrongly-shaped record (owner rule: no fallbacks, clean errors only).
    """
    for required in ("source", "source_id", "title"):
        if not raw.get(required):
            raise ValueError(f"activity missing required field '{required}': {raw!r}")

    city, state = _split_city_state(raw.get("location") or raw.get("city_state"))

    record = {"id": _derive_id(raw["source"], raw["source_id"]), "city": city, "state": state}
    for field in PUBLIC_ACTIVITY_FIELDS:
        if field in raw:
            record[field] = raw[field]

    brackets = raw.get("brackets")
    if brackets:
        record["brackets"] = [sanitize_bracket(b) for b in brackets]

    assert_no_pii(record)
    return record


def assert_no_pii(record: dict) -> None:
    """Raise AssertionError if any banned key or email/phone-shaped value survived.

    This is the guarantee: every record written to feed/data/ or served by
    feed/api.py has passed this check.
    """
    leaked_keys = _BANNED_KEYS & record.keys()
    assert not leaked_keys, f"PII key(s) leaked into sanitized record: {leaked_keys}"

    for key, value in record.items():
        if not isinstance(value, str):
            continue
        assert not _EMAIL_RE.search(value), f"email-shaped value leaked in field '{key}': {value!r}"
        assert not _PHONE_RE.search(value), f"phone-shaped value leaked in field '{key}': {value!r}"
