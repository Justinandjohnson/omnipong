"""Offline unit tests for the OmniPong agent's pure logic and wiring.

No network, no browser, no database — these only exercise the area-matching
rules in ``omnipong_config`` and the action/registry wiring in
``omnipong_agent`` / the MCP server.
"""

from __future__ import annotations

import asyncio

import pytest

from omnipong_config import (
    DEFAULT_AREA_CITIES,
    activity_in_area,
    area_cities,
    area_region,
    area_states,
)


def _activity(**overrides):
    base = {
        "title": "Spring Open",
        "city_state": "Plano, TX",
        "location": "Plano Table Tennis Club",
    }
    base.update(overrides)
    return base


# --- area matching ---------------------------------------------------------


def test_city_match():
    assert activity_in_area(_activity())


def test_city_match_is_case_insensitive():
    assert activity_in_area(_activity(city_state="AUSTIN, TX", location=""))


def test_state_only_match():
    # A city we don't list, but still in Texas.
    assert activity_in_area(
        _activity(city_state="Somewhere, TX", location="Community Center")
    )


def test_state_full_name_match():
    assert activity_in_area(_activity(city_state="El Paso, Texas", location=""))


def test_out_of_area_is_false():
    assert not activity_in_area(
        _activity(city_state="Denver, CO", location="Denver TTC")
    )


def test_empty_location_is_false():
    assert not activity_in_area({"title": "Nowhere", "city_state": "", "location": ""})


def test_explicit_cities_override():
    assert activity_in_area(_activity(city_state="Kansas City, MO"), cities=("kansas city",), states=())
    assert not activity_in_area(_activity(city_state="Plano, TX"), cities=("kansas city",), states=())


# --- config env handling ---------------------------------------------------


def test_defaults():
    assert area_region() == "8"
    assert "plano" in area_cities()
    assert area_states() == ("tx", "texas")


def test_env_overrides(monkeypatch):
    monkeypatch.setenv("AREA_REGION", "4")
    monkeypatch.setenv("AREA_CITIES", "Kansas City, St. Louis ")
    monkeypatch.setenv("AREA_STATES", "mo, ks")
    assert area_region() == "4"
    assert area_cities() == ("kansas city", "st. louis")
    assert area_states() == ("mo", "ks")


def test_blank_env_falls_back(monkeypatch):
    monkeypatch.setenv("AREA_CITIES", "   ")
    assert area_cities() == DEFAULT_AREA_CITIES


# --- action / MCP wiring ---------------------------------------------------


def test_unknown_action_errors():
    from omnipong_agent import run_action

    result = asyncio.run(run_action("does_not_exist"))
    assert result["status"] == "error"
    assert "does_not_exist" in result["message"]


def test_mcp_server_exposes_expected_tools():
    pytest.importorskip("mcp.server.fastmcp")
    import omnipong_mcp_server as server

    tools = asyncio.run(server.mcp.list_tools())
    names = {t.name for t in tools}
    assert {
        "check_new_tournaments",
        "signup_tournament",
        "search_player",
        "list_area_tournaments",
        "sync_data",
        "get_my_matches",
    } <= names
