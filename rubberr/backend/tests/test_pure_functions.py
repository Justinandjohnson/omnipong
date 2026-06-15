"""
Tests for pure (side-effect-free) logic in the Rubberr backend.

Because most Rubberr endpoints are tightly coupled to SQLAlchemy sessions,
we extract and test the business logic directly rather than hitting the DB.

Run from the project root (/Users/jjohnson/Desktop/omnipong) with:
    pip install pytest pytest-asyncio
    pytest rubberr/backend/tests/test_pure_functions.py -v
"""

import pytest


# ---------------------------------------------------------------------------
# Match result parsing helpers
# ---------------------------------------------------------------------------
# This logic appears repeatedly in main.py — extract it once for testing.

def parse_match_result(res_str) -> bool:
    """Return True if the match result string indicates a win."""
    if res_str in ("Win", "W"):
        return True
    if res_str and "-" in res_str:
        try:
            p1, p2 = map(int, res_str.split("-"))
            return p1 > p2
        except (ValueError, TypeError):
            pass
    return False


def parse_set_scores(sets_str: str) -> list[tuple[int, int]]:
    """Parse a set-scores string like '11-9, 9-11' into a list of (player, opp) tuples."""
    if not sets_str:
        return []
    parsed = []
    for s in sets_str.split(","):
        s = s.strip()
        if "-" in s:
            try:
                sp1, sp2 = map(int, s.split("-"))
                parsed.append((sp1, sp2))
            except ValueError:
                pass
    return parsed


def detect_comeback(is_win: bool, parsed_sets: list[tuple[int, int]]) -> bool:
    """True if player lost set 1 but won the match."""
    if not parsed_sets or not is_win:
        return False
    s1_user, s1_opp = parsed_sets[0]
    return s1_user < s1_opp and is_win


def detect_choke(is_win: bool, parsed_sets: list[tuple[int, int]]) -> bool:
    """True if player won set 1 but lost the match."""
    if not parsed_sets or is_win:
        return False
    s1_user, s1_opp = parsed_sets[0]
    return s1_user > s1_opp and not is_win


def count_close_sets(parsed_sets: list[tuple[int, int]]) -> tuple[int, int]:
    """Return (close_sets_won, close_sets_total) where close = diff <= 2."""
    swung = 0
    won = 0
    for sp1, sp2 in parsed_sets:
        if abs(sp1 - sp2) <= 2:
            swung += 1
            if sp1 > sp2:
                won += 1
    return won, swung


# ---------------------------------------------------------------------------
# Practice partner scoring helpers (extracted from get_practice_partners)
# ---------------------------------------------------------------------------


def compute_skill_score(rating_diff: float) -> float:
    """1.0 if within 50 pts, linear decay to 0 at 400 pts."""
    if rating_diff <= 50:
        return 1.0
    return max(0.0, 1.0 - (rating_diff / 400.0))


def compute_balance_score(wins: int, total: int) -> float:
    """Bell curve peaking at 0.5 win-rate."""
    if total == 0:
        return 0.0
    win_rate = wins / total
    return 1.0 - (abs(win_rate - 0.5) * 2)


def compute_competitiveness_score(close_matches: int, total: int) -> float:
    """Percent of close matches, boosted by 1.5x, capped at 1.0."""
    if total == 0:
        return 0.0
    return min(1.0, (close_matches / total) * 1.5)


def compute_weighted_score(
    skill_score: float,
    comp_score: float,
    balance_score: float,
    recent_score: float,
) -> float:
    """Weighted aggregate score for practice partner ranking."""
    return (
        (skill_score * 0.3)
        + (comp_score * 0.3)
        + (balance_score * 0.3)
        + (recent_score * 0.1)
    )


# ---------------------------------------------------------------------------
# Tests: parse_match_result
# ---------------------------------------------------------------------------


class TestParseMatchResult:
    def test_win_string(self):
        assert parse_match_result("Win") is True

    def test_w_string(self):
        assert parse_match_result("W") is True

    def test_numeric_win(self):
        assert parse_match_result("3-1") is True

    def test_numeric_loss(self):
        assert parse_match_result("1-3") is False

    def test_loss_string(self):
        assert parse_match_result("Loss") is False

    def test_none(self):
        assert parse_match_result(None) is False

    def test_empty_string(self):
        assert parse_match_result("") is False

    def test_tied_returns_false(self):
        assert parse_match_result("2-2") is False


# ---------------------------------------------------------------------------
# Tests: parse_set_scores
# ---------------------------------------------------------------------------


class TestParseSetScores:
    def test_single_set(self):
        assert parse_set_scores("11-9") == [(11, 9)]

    def test_multiple_sets(self):
        result = parse_set_scores("11-9, 9-11, 11-7")
        assert result == [(11, 9), (9, 11), (11, 7)]

    def test_empty_string(self):
        assert parse_set_scores("") == []

    def test_none_string(self):
        assert parse_set_scores(None) == []

    def test_malformed_ignored(self):
        result = parse_set_scores("11-9, bad, 11-7")
        assert result == [(11, 9), (11, 7)]


# ---------------------------------------------------------------------------
# Tests: detect_comeback / detect_choke
# ---------------------------------------------------------------------------


class TestComeback:
    def test_lost_set1_won_match(self):
        sets = [(9, 11), (11, 9), (11, 9)]
        assert detect_comeback(True, sets) is True

    def test_won_set1_won_match_not_comeback(self):
        sets = [(11, 9), (11, 9)]
        assert detect_comeback(True, sets) is False

    def test_lost_match_not_comeback(self):
        sets = [(9, 11), (9, 11)]
        assert detect_comeback(False, sets) is False

    def test_empty_sets_not_comeback(self):
        assert detect_comeback(True, []) is False


class TestChoke:
    def test_won_set1_lost_match(self):
        sets = [(11, 9), (9, 11), (9, 11)]
        assert detect_choke(False, sets) is True

    def test_lost_set1_lost_match_not_choke(self):
        sets = [(9, 11), (9, 11)]
        assert detect_choke(False, sets) is False

    def test_won_match_not_choke(self):
        sets = [(11, 9), (11, 9)]
        assert detect_choke(True, sets) is False

    def test_empty_sets_not_choke(self):
        assert detect_choke(False, []) is False


# ---------------------------------------------------------------------------
# Tests: count_close_sets
# ---------------------------------------------------------------------------


class TestCountCloseSets:
    def test_no_close_sets(self):
        won, swung = count_close_sets([(11, 5), (11, 3)])
        assert swung == 0
        assert won == 0

    def test_one_close_set_won(self):
        won, swung = count_close_sets([(11, 9), (11, 5)])
        assert swung == 1
        assert won == 1

    def test_one_close_set_lost(self):
        won, swung = count_close_sets([(9, 11), (11, 5)])
        assert swung == 1
        assert won == 0

    def test_multiple_close_sets(self):
        won, swung = count_close_sets([(11, 9), (11, 9), (9, 11)])
        assert swung == 3
        assert won == 2

    def test_empty(self):
        won, swung = count_close_sets([])
        assert won == 0
        assert swung == 0

    def test_deuce_set(self):
        # 12-10 is a close set (diff = 2)
        won, swung = count_close_sets([(12, 10)])
        assert swung == 1
        assert won == 1


# ---------------------------------------------------------------------------
# Tests: practice partner scoring
# ---------------------------------------------------------------------------


class TestSkillScore:
    def test_exact_match(self):
        assert compute_skill_score(0) == pytest.approx(1.0)

    def test_within_50_pts(self):
        assert compute_skill_score(50) == pytest.approx(1.0)

    def test_at_400_pts_diff(self):
        assert compute_skill_score(400) == pytest.approx(0.0)

    def test_beyond_400_clamped(self):
        assert compute_skill_score(500) == pytest.approx(0.0)

    def test_mid_range(self):
        # 200 pts diff → 1 - (200/400) = 0.5
        assert compute_skill_score(200) == pytest.approx(0.5)


class TestBalanceScore:
    def test_perfect_win_rate(self):
        # 50% win rate → max score
        assert compute_balance_score(5, 10) == pytest.approx(1.0)

    def test_zero_wins(self):
        # 0% win rate → min score
        assert compute_balance_score(0, 10) == pytest.approx(0.0)

    def test_all_wins(self):
        # 100% win rate → min score
        assert compute_balance_score(10, 10) == pytest.approx(0.0)

    def test_no_matches_returns_zero(self):
        assert compute_balance_score(0, 0) == pytest.approx(0.0)

    def test_40_percent_win_rate(self):
        # |0.4 - 0.5| = 0.1 → 1 - 0.2 = 0.8
        assert compute_balance_score(4, 10) == pytest.approx(0.8)


class TestCompetitivenessScore:
    def test_all_close_matches_boosted(self):
        # 100% close rate → min(1.0, 1.5) = 1.0
        assert compute_competitiveness_score(5, 5) == pytest.approx(1.0)

    def test_no_close_matches(self):
        assert compute_competitiveness_score(0, 5) == pytest.approx(0.0)

    def test_some_close(self):
        # 2/5 = 0.4 → 0.4 * 1.5 = 0.6
        assert compute_competitiveness_score(2, 5) == pytest.approx(0.6)

    def test_zero_total_returns_zero(self):
        assert compute_competitiveness_score(0, 0) == pytest.approx(0.0)


class TestWeightedScore:
    def test_all_perfect_gives_one(self):
        score = compute_weighted_score(1.0, 1.0, 1.0, 1.0)
        assert score == pytest.approx(1.0)

    def test_all_zero_gives_zero(self):
        score = compute_weighted_score(0.0, 0.0, 0.0, 0.0)
        assert score == pytest.approx(0.0)

    def test_weights_sum_to_one(self):
        # Verify the weight coefficients add to 1.0
        assert (0.3 + 0.3 + 0.3 + 0.1) == pytest.approx(1.0)

    def test_recent_activity_has_less_weight(self):
        # Score with high recent vs high skill should prefer skill
        skill_dominant = compute_weighted_score(1.0, 0.0, 0.0, 0.0)
        recent_dominant = compute_weighted_score(0.0, 0.0, 0.0, 1.0)
        assert skill_dominant > recent_dominant

    def test_typical_values(self):
        score = compute_weighted_score(0.8, 0.6, 0.9, 0.5)
        assert 0.0 < score < 1.0


# ---------------------------------------------------------------------------
# Tests: Texas city / region filtering (inline logic from /tournaments endpoint)
# ---------------------------------------------------------------------------

TX_CITIES = [
    "plano", "austin", "houston", "san antonio", "dallas",
    "richardson", "irving", "katy", "allen", "colleyville",
    "round rock", "fort worth", "lubbock", "el paso", "arlington",
]


def is_texas_location(location: str) -> bool:
    loc_lower = (location or "").lower()
    return any(city in loc_lower for city in TX_CITIES)


class TestTexasFilter:
    def test_dallas_is_texas(self):
        assert is_texas_location("Dallas Convention Center") is True

    def test_houston_is_texas(self):
        assert is_texas_location("Houston, TX") is True

    def test_new_york_is_not_texas(self):
        assert is_texas_location("New York City, NY") is False

    def test_empty_string(self):
        assert is_texas_location("") is False

    def test_none_string(self):
        assert is_texas_location(None) is False

    def test_case_insensitive(self):
        assert is_texas_location("PLANO") is True

    def test_round_rock(self):
        assert is_texas_location("Round Rock, TX") is True


# ---------------------------------------------------------------------------
# Tests: source → filter mapping (from /stats endpoint)
# ---------------------------------------------------------------------------


def source_to_filter(source: str) -> str:
    if source == "usatt":
        return "source = 'omnipong'"
    elif source == "arcade":
        return "source = 'arcade'"
    else:
        return "source IN ('stadium', 'stadium_league')"


class TestSourceFilter:
    def test_usatt_source(self):
        assert source_to_filter("usatt") == "source = 'omnipong'"

    def test_arcade_source(self):
        assert source_to_filter("arcade") == "source = 'arcade'"

    def test_club_source(self):
        assert "stadium" in source_to_filter("club")

    def test_default_is_stadium(self):
        assert "stadium" in source_to_filter("something_else")
