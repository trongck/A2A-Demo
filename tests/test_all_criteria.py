"""Kiểm thử contract Google Places V2 xuyên suốt MCP -> A2 -> A1."""

from agents.a0 import orchestrator
import agents.a1.server as a1
import agents.a2.server as a2
from mcp_server import server as mcp
from shared.data_adapter import DATA_PATH, DATA_REVISION, START_NODE_ID, load_raw_places
from shared.memory.database import get_or_create_session, init_db


def _local_mcp(tool_name, arguments):
    if tool_name == "get_attractions":
        return mcp.tool_get_attractions(arguments.get("scenario_id", "base"), arguments.get("service_ids"))
    if tool_name == "get_crowd_snapshots":
        return mcp.tool_get_crowd_snapshots(arguments.get("scenario_id", "base"), arguments.get("service_ids"))
    if tool_name == "get_route_matrix":
        return mcp.tool_get_route_matrix(arguments.get("node_ids", []))
    if tool_name == "get_weather":
        return mcp.tool_get_weather(arguments.get("start_at", ""), arguments.get("end_by", ""))
    return {}


def _request(**hard_overrides):
    hard = {
        "indoor_only": False,
        "max_thrill_level": "moderate",
        "max_wait_minutes_per_stop": 20,
        "budget_vnd_total": 150000,
        "min_end_buffer_minutes": 10,
        "allow_unknown_crowd": True,
        "excluded_service_ids": [],
        "min_activity_count": 3,
    }
    hard.update(hard_overrides)
    return {
        "start_at": "2026-09-19T10:00:00+07:00",
        "end_by": "2026-09-19T16:00:00+07:00",
        "start_node_id": START_NODE_ID,
        "end_node_id": START_NODE_ID,
        "group_members": [{"member_id": "adult_1", "age_years": 30, "height_cm": 170}],
        "hard_constraints": hard,
        "preferences": {},
        "number_of_plans": 2,
    }


def test_v2_is_the_only_runtime_source():
    rows = load_raw_places()
    assert DATA_PATH.name == "V-AI-Mock-Data-V2.json"
    assert len(rows) == 267
    assert all("placeId" in row and "location" in row for row in rows)


def test_mcp_normalizes_v2_fields():
    attractions = mcp.tool_get_attractions()
    assert len(attractions) > 10
    first = attractions[0]
    assert first["data_revision"] == DATA_REVISION
    assert first["service_id"] == first["source"]["place_id"]
    assert {"lat", "lng", "node_id"} <= first["location"].keys()
    assert "weekly_intervals" in first["schedule"]
    assert "rating" in first and "reviews_count" in first


def test_mcp_filters_and_routes_v2():
    rides = mcp.tool_get_attractions(categories=["ride"], limit=3)
    assert rides and all(item["category"] == "ride" for item in rides)
    matrix = mcp.tool_get_route_matrix([START_NODE_ID, rides[0]["service_id"]])["matrix"]
    assert matrix[START_NODE_ID][rides[0]["service_id"]]["reachable"] is True
    assert matrix[START_NODE_ID][rides[0]["service_id"]]["walking_minutes"] >= 1


def test_a2_preserves_missing_crowd_as_unknown(monkeypatch):
    monkeypatch.setattr(a2, "call_mcp_tool", _local_mcp)
    monkeypatch.setattr(a2, "is_llm_available", lambda: False)
    result = a2.analyze_crowd_logic()
    assert result["data_revision"] == DATA_REVISION
    assert result["items"]
    assert all(item["current_people"] is None for item in result["items"])
    assert all(item["wait_minutes"] is None for item in result["items"])
    assert all(item["load_category"] == "unknown" for item in result["items"])


def test_a1_builds_plans_from_v2(monkeypatch):
    monkeypatch.setattr(a1, "call_mcp_tool", _local_mcp)
    monkeypatch.setattr(a2, "call_mcp_tool", _local_mcp)
    monkeypatch.setattr(a1, "is_llm_available", lambda: False)
    monkeypatch.setattr(a2, "is_llm_available", lambda: False)
    analysis = a2.analyze_crowd_logic()
    result = a1.plan_itinerary_logic(_request(), analysis)
    assert result["status"] == "completed"
    assert result["data_revision"] == DATA_REVISION
    assert len(result["plans"]) == 2
    for plan in result["plans"]:
        assert plan["start_node_id"] == START_NODE_ID
        assert plan["end_node_id"] == START_NODE_ID
        assert len(plan["legs"]) >= 3


def test_a1_migrates_legacy_session_defaults(monkeypatch):
    monkeypatch.setattr(a1, "call_mcp_tool", _local_mcp)
    monkeypatch.setattr(a2, "call_mcp_tool", _local_mcp)
    monkeypatch.setattr(a1, "is_llm_available", lambda: False)
    monkeypatch.setattr(a2, "is_llm_available", lambda: False)
    analysis = a2.analyze_crowd_logic()
    request = _request(allow_unknown_crowd=False)
    request["start_node_id"] = "start_sea_hub"
    request["end_node_id"] = "start_sea_hub"

    result = a1.plan_itinerary_logic(request, analysis)

    assert result["status"] == "completed"
    assert all(plan["start_node_id"] == START_NODE_ID for plan in result["plans"])


def test_a1_reports_impossible_window(monkeypatch):
    monkeypatch.setattr(a1, "call_mcp_tool", _local_mcp)
    monkeypatch.setattr(a2, "call_mcp_tool", _local_mcp)
    monkeypatch.setattr(a1, "is_llm_available", lambda: False)
    monkeypatch.setattr(a2, "is_llm_available", lambda: False)
    analysis = a2.analyze_crowd_logic()
    request = _request(min_activity_count=5)
    request["end_by"] = "2026-09-19T10:30:00+07:00"
    result = a1.plan_itinerary_logic(request, analysis)
    assert result["status"] == "no_feasible_plan"
    assert result["unfeasible_reasons"]


def test_a1_rejects_non_v2_crowd_analysis():
    result = a1.plan_itinerary_logic(_request(), {"data_revision": "v1", "items": []})
    assert result["status"] == "failed"
    assert result["data_revision"] == DATA_REVISION
    assert result["errors"]


def test_a0_still_requests_missing_input(monkeypatch):
    monkeypatch.setattr(orchestrator, "is_llm_available", lambda: False)
    _, complete, missing, intent, routing = orchestrator.extract_or_update_request(
        "Lên lịch tham quan VinWonders", {"profile": {}},
    )
    assert complete is False
    assert intent == "plan_itinerary"
    assert missing
    assert routing["status"] == "need_clarification"


def test_session_isolation_is_data_revision_agnostic():
    init_db()
    left = get_or_create_session("sess_v2_left", "base")
    right = get_or_create_session("sess_v2_right", "base")
    assert left["session_id"] != right["session_id"]
