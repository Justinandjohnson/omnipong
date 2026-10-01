"""Central configuration for the OmniPong agent.

Everything that used to be hard-coded personal/regional data in
``daily_check.py`` (the "Region 8 / Texas city list") now lives here, read
from the environment with safe defaults. Keep this module dependency-free
(only ``os``/``dotenv``) so both the CLI and the MCP server can import it
without pulling in Playwright or SQLAlchemy.
"""

from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

# OmniPong regional search uses a numeric region id in
# ``T-tourney.asp?t=<region>&Region=<region>``. 8 = Texas region.
DEFAULT_AREA_REGION = "8"

# Cities used to decide whether a scraped activity is "in the area". Matched
# case-insensitively as substrings of the activity's location string, so
# "Plano" matches "Plano, TX". Override with AREA_CITIES="a,b,c".
DEFAULT_AREA_CITIES: tuple[str, ...] = (
    "plano",
    "austin",
    "houston",
    "san antonio",
    "dallas",
    "richardson",
    "irving",
    "katy",
    "allen",
    "colleyville",
    "round rock",
    "fort worth",
    "lubbock",
    "el paso",
    "arlington",
    "mckinney",
    "frisco",
    "carrollton",
    "garland",
    "denton",
    "waco",
    "college station",
)

# State tokens accepted as an area match even when no listed city appears.
DEFAULT_AREA_STATES: tuple[str, ...] = ("tx", "texas")


def area_region() -> str:
    """The OmniPong region id to monitor (default ``"8"`` = Texas)."""
    return os.getenv("AREA_REGION", DEFAULT_AREA_REGION).strip() or DEFAULT_AREA_REGION


def area_cities() -> tuple[str, ...]:
    """Cities that count as "in the area".

    Reads ``AREA_CITIES`` (comma-separated). Falls back to
    :data:`DEFAULT_AREA_CITIES` when unset or blank. Values are lowercased and
    trimmed so matching is case-insensitive.
    """
    raw = os.getenv("AREA_CITIES")
    if raw is None or not raw.strip():
        return DEFAULT_AREA_CITIES
    cities = tuple(c.strip().lower() for c in raw.split(",") if c.strip())
    return cities or DEFAULT_AREA_CITIES


def area_states() -> tuple[str, ...]:
    """State tokens accepted as an area match (default Texas)."""
    raw = os.getenv("AREA_STATES")
    if raw is None or not raw.strip():
        return DEFAULT_AREA_STATES
    states = tuple(s.strip().lower() for s in raw.split(",") if s.strip())
    return states or DEFAULT_AREA_STATES


def _activity_location(activity: dict) -> str:
    """Join the location-ish fields of a scraped activity into one string."""
    parts = [
        activity.get("city_state"),
        activity.get("location"),
        activity.get("location_city"),
    ]
    return " ".join(p for p in parts if p).lower()


def activity_in_area(
    activity: dict,
    *,
    cities: tuple[str, ...] | None = None,
    states: tuple[str, ...] | None = None,
) -> bool:
    """True if a scraped activity's location is inside the configured area.

    Pure function (no I/O) so it is cheap to unit-test. Matches a listed city
    OR a state token (``", tx"`` / ``", texas"``) anywhere in the location
    string.
    """
    location = _activity_location(activity)
    if not location:
        return False

    if any(city in location for city in (cities if cities is not None else area_cities())):
        return True

    for state in states if states is not None else area_states():
        if f", {state}" in location or location.strip().endswith(state):
            return True
    return False
