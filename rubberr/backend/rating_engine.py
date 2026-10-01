"""USATT-aware tournament/event recommendation engine.

Encodes the official USATT rating-exchange table and an Elo-style win
probability so we can estimate, for a given player rating and a candidate
event, the *expected rating-point change* and the chance of winning at least
one match. Combined with a "play up modestly" preference, this ranks which
events — and therefore which tournaments — are most worth entering.

This module is intentionally pure (no database, no network) so it can be
unit-tested offline and reused by the API, the daily scout, and the MCP agent.

Rating model notes
------------------
USATT exchanges a fixed number of points per match based on the gap between
the two players' ratings. The table below is the long-standing USATT/league
chart (spread = higher_rated - lower_rated):

    spread        higher wins   lower wins (upset)
    0-12              8               8
    13-37             7              10
    38-62             6              13
    63-87             5              16
    88-112            4              20
    113-137           3              25
    138-162           2              30
    163-187           2              35
    188-212           1              40
    213-237           1              45
    238+              0              50

The key asymmetry we exploit: playing *up* has a capped downside (losing to a
much stronger player costs ~0), while playing *down* has a capped upside and a
large downside. So the engine prefers events where the expected field sits at
or slightly above the player's rating.
"""

from __future__ import annotations

# (inclusive upper bound of the rating spread, points for the higher-rated win,
#  points for the lower-rated win)
EXCHANGE_TABLE: list[tuple[int, int, int]] = [
    (12, 8, 8),
    (37, 7, 10),
    (62, 6, 13),
    (87, 5, 16),
    (112, 4, 20),
    (137, 3, 25),
    (162, 2, 30),
    (187, 2, 35),
    (212, 1, 40),
    (237, 1, 45),
    (10**9, 0, 50),
]

# Elo divisor. 400 is the classic value; table tennis ratings behave a little
# steeper but 400 keeps the estimates conservative (fewer false "upsets").
ELO_DIVISOR = 400.0

# Typical number of matches a player plays in one event (round robin + bracket).
DEFAULT_MATCHES_PER_EVENT = 4

# Assume the strongest eligible players enter an "Under X" bracket, so the
# average opponent sits a little below the cap.
BRACKET_FIELD_MARGIN = 100

# Fallback expected field rating for an Open/Championship event with no cap.
DEFAULT_OPEN_FIELD_RATING = 2200

# "Play up modestly": the ideal gap between the field and the player.
IDEAL_GAP_LO = 0
IDEAL_GAP_HI = 200

# Minimum chance of winning at least one match in an event for us to call it
# "recommended". 0.4 keeps genuinely winnable-but-stretching events in play.
WIN_LIKELY_THRESHOLD = 0.4


def exchange_points(spread: int) -> tuple[int, int]:
    """Return (points if the higher-rated player wins, points if the lower wins).

    ``spread`` is ``higher_rating - lower_rating`` and must be >= 0.
    """
    spread = abs(int(spread))
    for upper, expected, upset in EXCHANGE_TABLE:
        if spread <= upper:
            return expected, upset
    return 0, 50


def expected_win_probability(
    player_rating: float, opponent_rating: float, divisor: float = ELO_DIVISOR
) -> float:
    """Elo-style probability that ``player_rating`` beats ``opponent_rating``."""
    return 1.0 / (1.0 + 10.0 ** ((opponent_rating - player_rating) / divisor))


def estimate_field_rating(
    event_name: str,
    rating_limit: int | None,
    open_field_rating: float = DEFAULT_OPEN_FIELD_RATING,
) -> float:
    """Estimate the average opponent rating for an event.

    ``rating_limit`` is the event's cap (e.g. 1700 for "Under 1700"), or None
    for Open/Championship events.
    """
    if rating_limit:
        return max(800.0, float(rating_limit) - BRACKET_FIELD_MARGIN)
    # Open events. Try to read a number out of the name as a hint, else fall
    # back to a strong default field.
    return float(open_field_rating)


def target_fit(spread: float) -> float:
    """1.0 when the field sits in the ideal 'play up modestly' window, decaying
    outside it; penalises playing down harder than playing up too far."""
    if IDEAL_GAP_LO <= spread <= IDEAL_GAP_HI:
        return 1.0
    if spread < IDEAL_GAP_LO:
        # Playing down: upside is capped and losses are costly.
        return max(0.0, 1.0 - (IDEAL_GAP_LO - spread) / 150.0)
    # Playing up too far: big upside but likely no wins.
    return max(0.0, 1.0 - (spread - IDEAL_GAP_HI) / 400.0)


def win_likely(p_at_least_one_win: float) -> bool:
    return p_at_least_one_win >= WIN_LIKELY_THRESHOLD


def competitiveness_label(spread: float) -> str:
    """Human label describing how the event sits relative to the player."""
    if spread <= -100:
        return "Playing down"
    if spread < 0:
        return "Favored"
    if spread <= 150:
        return "Competitive"
    if spread <= 350:
        return "Challenge"
    return "Reach"


def evaluate_event(
    event: dict,
    user_rating: float,
    *,
    matches: int = DEFAULT_MATCHES_PER_EVENT,
    open_field_rating: float = DEFAULT_OPEN_FIELD_RATING,
) -> dict:
    """Score a single event for a player.

    Returns a dict with the recommendation, expected rating change, win
    probability, and a human-readable reason. Never raises on missing fields.
    """
    name = str(event.get("name") or "").strip()
    limit = event.get("rating_limit")
    if limit in ("", 0):
        limit = None
    if limit is not None:
        try:
            limit = int(limit)
        except (TypeError, ValueError):
            limit = None

    eligible = limit is None or user_rating <= limit
    field = estimate_field_rating(name, limit, open_field_rating=open_field_rating)
    spread = field - user_rating

    base = {
        "name": name,
        "rating_limit": limit,
        "fee": event.get("fee"),
        "estimated_field_rating": round(field),
    }

    if not eligible:
        return {
            **base,
            "eligible": False,
            "win_probability": 0.0,
            "expected_rating_change": 0,
            "upside": 0,
            "downside": 0,
            "p_at_least_one_win": 0.0,
            "competitiveness": "Not eligible",
            "recommended": False,
            "score": -999.0,
            "reason": f"Your rating is above the {limit} cap.",
        }

    p = expected_win_probability(user_rating, field)

    exp_pts, upset_pts = exchange_points(abs(spread))
    if spread >= 0:  # field is stronger than the player
        win_change, loss_change = upset_pts, -exp_pts
    else:  # field is weaker than the player
        win_change, loss_change = exp_pts, -upset_pts

    per_match = p * win_change + (1.0 - p) * loss_change
    expected_total = per_match * matches
    p_at_least_one = 1.0 - (1.0 - p) ** matches

    fit = target_fit(spread)
    score = expected_total + fit * 15.0 + p_at_least_one * 10.0

    recommended = expected_total > 0 and win_likely(p_at_least_one)

    if recommended:
        reason = (
            f"Expected {expected_total:+.1f} rating pts over ~{matches} matches "
            f"vs an estimated {round(field)} field ({p_at_least_one:.0%} to win "
            f"at least one)."
        )
    elif not win_likely(p_at_least_one):
        reason = (
            f"Field (~{round(field)}) is a reach: only {p_at_least_one:.0%} to "
            "win a match."
        )
    else:
        reason = "Playing down — little upside and a costly downside."

    return {
        **base,
        "eligible": True,
        "win_probability": round(p, 3),
        "expected_rating_change": round(expected_total, 1),
        "upside": win_change,
        "downside": loss_change,
        "p_at_least_one_win": round(p_at_least_one, 3),
        "competitiveness": competitiveness_label(spread),
        "recommended": recommended,
        "score": round(score, 2),
        "reason": reason,
    }


def rank_events(
    events: list[dict],
    user_rating: float,
    *,
    top_n: int = 2,
    open_field_rating: float = DEFAULT_OPEN_FIELD_RATING,
) -> list[dict]:
    """Evaluate and rank all events, returning the top ``top_n`` recommended.

    If no event is strictly recommended, the highest-scoring eligible one is
    still returned (so the caller always has something to show), flagged as
    ``recommended=False``.
    """
    scored = [
        evaluate_event(e, user_rating, open_field_rating=open_field_rating)
        for e in events
        if e.get("name")
    ]
    eligible = [e for e in scored if e["eligible"]]
    eligible.sort(key=lambda e: e["score"], reverse=True)

    picked = [e for e in eligible if e["recommended"]][:top_n]
    if not picked and eligible:
        picked = eligible[:1]
    return picked


def build_tournament_recommendation(
    tournament: dict,
    events: list[dict],
    user_rating: float,
    *,
    top_n: int = 2,
) -> dict:
    """Build the recommendation block for one tournament."""
    rec_events = rank_events(events, user_rating, top_n=top_n)

    expected_change = round(
        sum(e.get("expected_rating_change", 0) for e in rec_events), 1
    )
    recommended = bool(rec_events) and any(e["recommended"] for e in rec_events)

    # Prioritise by the best single-event expected gain plus how winnable it is.
    best = rec_events[0] if rec_events else None
    priority = 0.0
    if best:
        priority = best.get("score", 0.0)

    if recommended and best:
        reason = (
            f"Enter {best['name']} ({best['competitiveness']}) — "
            f"{best['reason']}"
        )
    elif best:
        reason = best["reason"]
    else:
        reason = "No eligible events found for your rating."

    return {
        "recommended_events": rec_events,
        "expected_rating_change": expected_change,
        "recommended": recommended,
        "priority_score": round(priority, 2),
        "reason": reason,
    }
