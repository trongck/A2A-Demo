"""
Bộ kiểm thử toàn diện nghiệm thu 10 tiêu chí theo mục 10 của V-AI-Implementation-Plan.md.
"""

import json
from pathlib import Path
import pytest

from agents.a0.orchestrator import run_orchestration
from agents.a1.server import plan_itinerary_logic, validate_plan
from agents.a2.server import analyze_crowd_logic
from mcp_server.server import (
    tool_get_attractions,
    tool_get_crowd_snapshots,
    tool_get_route_matrix,
    tool_get_weather,
)
from shared.memory.database import (
    get_events,
    get_messages,
    get_or_create_session,
    init_db,
)

DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "V-AI-Mock-Data.json"


@pytest.fixture(scope="session", autouse=True)
def setup_database():
    init_db()


def load_raw_data():
    with open(DATA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


# Ca 1: Baseline
def test_acceptance_baseline():
    data = load_raw_data()
    req = data["demo_requests"][0]
    res = run_orchestration(
        session_id="test_sess_baseline",
        user_message=req["message"],
        scenario_override="base",
        preset_data=req,
    )
    assert res["status"] == "completed"
    assert len(res["plans"]) >= 2, "Phải có ít nhất 2 phương án"

    for p in res["plans"]:
        assert len(p["legs"]) >= 3, "Mỗi phương án phải có ít nhất 3 hoạt động"
        assert p["end_buffer_minutes"] >= 10, "Thời gian dự phòng phải >= 10 phút"
        assert p["total_duration_minutes"] <= 120, "Phải kết thúc trước 16:00 (120 phút)"
        assert p["end_node_id"] == "start_sea_hub", "Phải về đúng điểm xuất phát"


# Ca 2: Input thiếu
def test_acceptance_missing_input():
    res = run_orchestration(
        session_id="test_sess_missing",
        user_message="Chào bạn, hãy gợi ý cho tôi vài trò chơi vui ở VinWonders nhé",
    )
    assert res["status"] == "needs_input", "A0 phải hỏi lại khi thiếu thông tin"
    assert len(res["missing_fields"]) > 0
    assert "thông_tin_thành_viên" in res["missing_fields"] or "khung_giờ_tham_quan" in res["missing_fields"]


# Ca 3: Multi-turn trong cùng phiên
def test_acceptance_multiturn_same_session():
    data = load_raw_data()
    req = data["demo_requests"][0]
    sess_id = "test_sess_multiturn"

    # Lượt 1: Nạp preset
    res1 = run_orchestration(sess_id, req["message"], preset_data=req)
    assert res1["status"] == "completed"

    # Lượt 2: Chat chỉnh sửa trong cùng phiên
    res2 = run_orchestration(sess_id, "Chỉ đi trong nhà, tối thiểu 2 điểm")
    assert res2["status"] == "completed"
    assert len(res2["plans"]) >= 1

    for p in res2["plans"]:
        for leg in p["legs"]:
            assert leg["indoor"] is True, f"Điểm {leg['service_name']} phải là trong nhà"


# Ca 4: Tăng mật độ (aquarium_crowded)
def test_acceptance_aquarium_crowded():
    data = load_raw_data()
    req = data["demo_requests"][0]

    # Phân tích A2 thấy Thủy cung chờ 35p
    a2_res = analyze_crowd_logic(scenario_id="aquarium_crowded")
    aq_item = next(x for x in a2_res["items"] if x["service_id"] == "poi_01")
    assert aq_item["wait_minutes"] == 35, "Thủy cung phải có thời gian chờ 35 phút"

    # A1 không chọn điểm này do max_wait_minutes_per_stop = 20
    plan_res = plan_itinerary_logic(req, a2_res, scenario_id="aquarium_crowded")
    assert plan_res["status"] == "completed"
    for p in plan_res["plans"]:
        assert "poi_01" not in p["service_ids"], "Lịch trình không được chứa Thủy cung vì vượt max_wait 20p"


# Ca 5: Đóng điểm (alpine_closed)
def test_acceptance_alpine_closed():
    data = load_raw_data()
    req = data["demo_requests"][0]

    a2_res = analyze_crowd_logic(scenario_id="alpine_closed")
    alp_item = next(x for x in a2_res["items"] if x["service_id"] == "poi_03")
    assert alp_item["operating_status"] == "temporarily_closed"
    assert alp_item["wait_minutes"] is None

    plan_res = plan_itinerary_logic(req, a2_res, scenario_id="alpine_closed")
    assert plan_res["status"] == "completed"
    for p in plan_res["plans"]:
        assert "poi_03" not in p["service_ids"], "Lịch trình không được chọn Alpine Coaster đang đóng"


# Ca 6: Dữ liệu cũ (Stale detection)
def test_acceptance_stale_data():
    a2_res = analyze_crowd_logic(scenario_id="base")
    poi10_item = next(x for x in a2_res["items"] if x["service_id"] == "poi_10")
    assert poi10_item["is_stale"] is True, "poi_10 snapshot lúc 13:40 so với 14:00 (>180s) phải được đánh dấu stale"


# Ca 7: Thiếu dữ liệu (missing_flying_cinema)
def test_acceptance_missing_data_no_zero_coercion():
    a2_res = analyze_crowd_logic(scenario_id="missing_flying_cinema")
    cinema_item = next(x for x in a2_res["items"] if x["service_id"] == "poi_02")
    assert cinema_item["current_people"] is None, "current_people thiếu tuyệt đối không được đổi thành 0"
    assert cinema_item["load_category"] == "unknown"


# Ca 8: Ràng buộc không khả thi
def test_acceptance_no_feasible_plan():
    impossible_req = {
        "start_at": "2026-09-18T14:00:00+07:00",
        "end_by": "2026-09-18T14:30:00+07:00",  # Chỉ có 30 phút
        "start_node_id": "start_sea_hub",
        "end_node_id": "start_sea_hub",
        "group_members": [{"member_id": "m1", "age_years": 30, "height_cm": 170}],
        "hard_constraints": {
            "indoor_only": False,
            "max_thrill_level": "moderate",
            "max_wait_minutes_per_stop": 20,
            "budget_vnd_total": 150000,
            "min_end_buffer_minutes": 10,
            "allow_unknown_crowd": False,
            "excluded_service_ids": [],
            "min_activity_count": 5,  # 5 điểm trong 30 phút là bất khả thi
        },
        "preferences": {},
        "number_of_plans": 1,
    }
    a2_res = analyze_crowd_logic(scenario_id="base")
    res = plan_itinerary_logic(impossible_req, a2_res, scenario_id="base")
    assert res["status"] == "no_feasible_plan"
    assert len(res["unfeasible_reasons"]) > 0


# Ca 9: Cô lập dữ liệu giữa 2 phiên
def test_acceptance_session_isolation():
    s1 = get_or_create_session("sess_iso_1", "aquarium_crowded")
    s2 = get_or_create_session("sess_iso_2", "alpine_closed")
    assert s1["scenario_id"] == "aquarium_crowded"
    assert s2["scenario_id"] == "alpine_closed"
    assert s1["session_id"] != s2["session_id"]


# Ca 10: Event Audit Trail
def test_acceptance_event_audit_trail():
    events = get_events("test_sess_baseline")
    assert len(events) >= 5, "Phiên baseline phải ghi nhận đầy đủ chuỗi sự kiện A0, A2, A1"
    event_types = [e["event_type"] for e in events]
    assert "user_message" in event_types
    assert "a0_intent" in event_types
    assert "a0_call_a2" in event_types
    assert "a2_result" in event_types
    assert "a0_call_a1" in event_types
    assert "a1_result" in event_types
    assert "a0_reply" in event_types
