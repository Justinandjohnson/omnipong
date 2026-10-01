"""Offline tests for the USATT rating/recommendation engine."""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "rubberr", "backend"))
)

from rating_engine import (  # noqa: E402
    build_tournament_recommendation,
    estimate_field_rating,
    evaluate_event,
    exchange_points,
    expected_win_probability,
    rank_events,
    target_fit,
)


def test_exchange_table_boundaries():
    assert exchange_points(0) == (8, 8)
    assert exchange_points(12) == (8, 8)
    assert exchange_points(13) == (7, 10)
    assert exchange_points(62) == (6, 13)
    assert exchange_points(87) == (5, 16)
    assert exchange_points(112) == (4, 20)
    assert exchange_points(238) == (0, 50)
    assert exchange_points(5000) == (0, 50)
    # symmetric for negative input (abs)
    assert exchange_points(-13) == (7, 10)


def test_expected_win_probability():
    assert abs(expected_win_probability(1500, 1500) - 0.5) < 1e-9
    assert expected_win_probability(1900, 1500) > 0.9
    assert expected_win_probability(1500, 1900) < 0.1


def test_estimate_field_rating():
    assert estimate_field_rating("Under 1700 RR", 1700) == 1600
    assert estimate_field_rating("Open Singles", None) == 2200
    assert estimate_field_rating("Open Singles", None, open_field_rating=2350) == 2350


def test_target_fit_prefers_playing_up_modestly():
    assert target_fit(0) == 1.0
    assert target_fit(150) == 1.0
    assert target_fit(200) == 1.0
    # playing down is penalised
    assert target_fit(-300) < 0.5
    # playing up too far decays (harder than the ideal window)
    assert 0.0 <= target_fit(600) < target_fit(200)


def test_evaluate_event_recommends_play_up_bracket():
    # A 1500 player in an Under 1800 bracket faces an est. ~1700 field: the
    # sweet spot — real upside, still winnable.
    ev = evaluate_event({"name": "Under 1800", "rating_limit": 1800, "fee": 40}, 1500)
    assert ev["eligible"] is True
    assert ev["recommended"] is True
    assert ev["expected_rating_change"] > 0
    assert ev["win_probability"] > 0
    assert ev["p_at_least_one_win"] >= 0.5
    assert ev["competitiveness"] in {"Competitive", "Challenge"}


def test_evaluate_event_flags_ineligible_over_cap_bracket():
    ev = evaluate_event({"name": "Under 1500", "rating_limit": 1500}, 1600)
    assert ev["eligible"] is False
    assert ev["recommended"] is False
    assert ev["score"] == -999.0


def test_evaluate_event_penalises_playing_down():
    # A 2000 player in an Open field that (unusually) sits well below them.
    ev = evaluate_event(
        {"name": "Open Singles", "rating_limit": None}, 2000, open_field_rating=1400
    )
    assert ev["eligible"] is True
    assert ev["recommended"] is False
    assert ev["expected_rating_change"] <= 0
    assert ev["competitiveness"] == "Playing down"


def test_evaluate_event_open_is_a_reach_for_mid_player():
    ev = evaluate_event({"name": "Open Singles", "rating_limit": None}, 1500)
    assert ev["eligible"] is True
    assert ev["recommended"] is False  # unlikely to win a match
    assert ev["competitiveness"] == "Reach"


def test_rank_events_orders_and_limits():
    events = [
        {"name": "Under 2200", "rating_limit": 2200},
        {"name": "Under 1800", "rating_limit": 1800},
        {"name": "Under 1500", "rating_limit": 1500},  # ineligible for 1600
    ]
    ranked = rank_events(events, 1600, top_n=2)
    assert len(ranked) <= 2
    assert all(e["eligible"] for e in ranked)
    assert any(e["recommended"] for e in ranked)


def test_rank_events_falls_back_to_best_eligible_when_none_recommended():
    # A very strong player facing only Open events: nothing is "recommended"
    # but we still return the best eligible so the UI has something to show.
    events = [{"name": "Open Singles", "rating_limit": None}]
    ranked = rank_events(events, 2600, top_n=2)
    assert len(ranked) == 1
    assert ranked[0]["recommended"] is False


def test_build_tournament_recommendation_shape():
    rec = build_tournament_recommendation(
        {"title": "Fall Open"},
        [
            {"name": "Under 1800", "rating_limit": 1800},
            {"name": "Under 1500", "rating_limit": 1500},
        ],
        1500,
    )
    assert set(rec) == {
        "recommended_events",
        "expected_rating_change",
        "recommended",
        "priority_score",
        "reason",
    }
    assert isinstance(rec["recommended_events"], list)
    assert rec["recommended"] is True
    assert rec["reason"]
