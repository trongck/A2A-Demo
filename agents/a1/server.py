"""
Agent A1: Planner Specialist.
Chạy trên cổng 8001.
A2A Server cung cấp Agent Card và Skill lập lịch trình.
Triển khai thuật toán tìm kiếm cắt nhánh (Branch and Bound) và bộ Validator xác định.
Bám sát mục 4 và mục 7 của V-AI-Implementation-Plan.md.
"""

from datetime import datetime, timedelta
import itertools
import json
from pathlib import Path
import re
from typing import Any

import httpx
from pydantic import BaseModel, Field
import uvicorn

from shared.security import get_logger, require_internal_secret
from shared.security.config import V_AI_INTERNAL_SECRET, INTERNAL_AUTH_ENABLED

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.apps import A2AFastAPIApplication
from a2a.server.events import EventQueue
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import (
    AgentCapabilities,
    AgentCard,
    AgentSkill,
    Message,
    Role,
    TextPart,
)
from fastapi import Depends
from shared.llm import (
    call_llm,
    generate_plan_rationale_with_llm,
    generate_unfeasible_explanation_with_llm,
    is_llm_available,
)
from shared.data_adapter import DATA_REVISION, START_NODE_ID, calculate_entry_ticket, members_to_ticket_groups

import os

MCP_URL = os.environ.get("MCP_URL", "http://127.0.0.1:8003")

logger = get_logger("a1.planner")

# L3: Giới hạn cứng cho tìm kiếm permutation, chống DoS
MAX_SEARCH_ITERATIONS = 5000



def call_mcp_tool(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Gọi công cụ qua MCP Server HTTP endpoint với caller_agent=a1_planner_specialist."""
    try:
        # H5: Gửi internal secret header
        headers: dict[str, str] = {}
        if INTERNAL_AUTH_ENABLED:
            headers["X-Internal-Secret"] = V_AI_INTERNAL_SECRET
        with httpx.Client(timeout=3.0) as client:
            resp = client.post(
                f"{MCP_URL}/api/tools/call",
                headers=headers,
                json={
                    "tool_name": tool_name,
                    "arguments": arguments,
                    "caller_agent": "a1_planner_specialist",
                },
            )
            if resp.status_code == 200:
                return resp.json().get("result", {})
    except Exception:
        pass


    from mcp_server.server import (
        tool_get_attractions,
        tool_get_crowd_snapshots,
        tool_get_route_matrix,
        tool_get_weather,
    )
    if tool_name == "get_attractions":
        return tool_get_attractions(
            arguments.get("scenario_id", "base"), arguments.get("service_ids"),
            arguments.get("categories"), arguments.get("limit"), arguments.get("scope", "vinwonders"),
        )
    elif tool_name == "get_crowd_snapshots":
        return tool_get_crowd_snapshots(
            arguments.get("scenario_id", "base"), arguments.get("service_ids"), arguments.get("scope", "vinwonders"),
        )
    elif tool_name == "get_route_matrix":
        return tool_get_route_matrix(arguments.get("node_ids", []))
    elif tool_name == "get_weather":
        return tool_get_weather(arguments.get("start_at", ""), arguments.get("end_by", ""))
    return {}


# --- Bảng chuyển đổi cấp độ cảm giác mạnh ---
THRILL_ORDER = {"none": 0, "low": 1, "moderate": 2, "high": 3, "extreme": 4}
MAX_PLANNING_CANDIDATES = 8


def is_open_for_visit(schedule: dict[str, Any], start: datetime, end: datetime) -> bool:
    """Kiểm tra khoảng ghé thăm theo weekly_intervals chuẩn hóa từ V2."""
    weekly = schedule.get("weekly_intervals", {})
    if not weekly:
        return True
    intervals = weekly.get(str(start.weekday()), [])
    start_minute = start.hour * 60 + start.minute
    end_minute = end.hour * 60 + end.minute
    for open_at, close_at in intervals:
        open_hour, open_minute = map(int, open_at.split(":"))
        close_hour, close_minute = map(int, close_at.split(":"))
        open_value = open_hour * 60 + open_minute
        close_value = close_hour * 60 + close_minute
        if close_value <= open_value:
            close_value += 24 * 60
        if open_value <= start_minute and end_minute <= close_value:
            return True
    return False


def is_eligible_for_group(attraction: dict[str, Any], members: list[dict[str, Any]]) -> tuple[bool, str]:
    """Kiểm tra mọi thành viên trong đoàn có đủ điều kiện tham gia điểm này không."""
    elig = attraction.get("eligibility", {})
    min_h = elig.get("min_height_cm") or 0
    max_h = elig.get("max_height_cm")
    min_age = elig.get("min_age_years") or 0
    adult_req_age = elig.get("adult_required_under_age_years")

    has_adult = any(m.get("age_years", 0) >= 18 for m in members)

    for m in members:
        h = m.get("height_cm", 0)
        age = m.get("age_years", 0)
        mid = m.get("member_id", "member")

        if h < min_h:
            return False, f"{mid} (cao {h}cm) không đạt chiều cao tối thiểu {min_h}cm"
        if max_h is not None and h > max_h:
            return False, f"{mid} (cao {h}cm) vượt chiều cao tối đa {max_h}cm"
        if age < min_age:
            return False, f"{mid} ({age} tuổi) không đạt tuổi tối thiểu {min_age}"
        if adult_req_age is not None and age < adult_req_age and not has_adult:
            return False, f"{mid} dưới {adult_req_age} tuổi cần người lớn đi kèm"

    return True, ""


# --- Bộ Validator Xác định (Deterministic Validator) ---

def validate_plan(
    plan: dict[str, Any],
    req: dict[str, Any],
    attractions_map: dict[str, Any],
    crowd_map: dict[str, Any],
    weather_windows: list[dict[str, Any]],
) -> tuple[bool, list[str]]:
    """Xác thực toàn bộ ràng buộc cứng đối với một phương án lịch trình đã sinh."""
    violations = []
    hard = req.get("hard_constraints", {})
    indoor_only = hard.get("indoor_only", False)
    max_thrill = hard.get("max_thrill_level", "moderate")
    max_wait = hard.get("max_wait_minutes_per_stop", 20)
    budget_total = hard.get("budget_vnd_total")
    min_buffer = hard.get("min_end_buffer_minutes", 10)
    min_act = hard.get("min_activity_count", 3)
    members = req.get("group_members", [])

    legs = plan.get("legs", [])
    if len(legs) < min_act:
        violations.append(f"Số lượng hoạt động ({len(legs)}) ít hơn tối thiểu yêu cầu ({min_act})")

    # Ràng buộc chi phí
    total_cost = plan.get("total_cost_vnd", 0)
    if budget_total is not None and total_cost > budget_total:
        violations.append(f"Tổng chi phí {total_cost:,} VND vượt ngân sách {budget_total:,} VND")

    # Ràng buộc buffer
    buffer_min = plan.get("end_buffer_minutes", 0)
    if buffer_min < min_buffer:
        violations.append(f"Thời gian dự phòng cuối ({buffer_min:.0f} phút) nhỏ hơn mức tối thiểu ({min_buffer} phút)")

    for leg in legs:
        sid = leg["service_id"]
        attr = attractions_map.get(sid)
        if not attr:
            violations.append(f"Không tìm thấy thông tin điểm {sid}")
            continue

        # Kiểm tra đóng cửa
        snap = crowd_map.get(sid, {})
        if snap.get("operating_status") == "temporarily_closed":
            violations.append(f"Điểm {attr['name']} ({sid}) đang tạm ngưng hoạt động")

        # Kiểm tra chỉ trong nhà
        if indoor_only and not attr.get("indoor", False):
            violations.append(f"Điểm {attr['name']} ngoài trời, vi phạm yêu cầu chỉ trong nhà")

        # Kiểm tra độ cảm giác mạnh
        thrill = attr.get("thrill_level", "none")
        if THRILL_ORDER.get(thrill, 0) > THRILL_ORDER.get(max_thrill, 2):
            violations.append(f"Điểm {attr['name']} có cảm giác mạnh ({thrill}) vượt mức cho phép ({max_thrill})")

        # Kiểm tra thời gian chờ
        wait_min = leg.get("wait_minutes", 0)
        if wait_min > max_wait:
            violations.append(f"Điểm {attr['name']} có thời gian chờ {wait_min} phút vượt mức tối đa {max_wait} phút")

        # Kiểm tra thành viên
        eligible, reason = is_eligible_for_group(attr, members)
        if not eligible:
            violations.append(f"Điểm {attr['name']} không đủ điều kiện: {reason}")

    return len(violations) == 0, violations


# --- Thuật toán lập lịch (Branch and Bound Search) ---

def plan_itinerary_logic(
    normalized_request: dict[str, Any],
    crowd_analysis: dict[str, Any],
    scenario_id: str = "base",
) -> dict[str, Any]:
    """Tìm kiếm và tạo các phương án lịch trình tối ưu, kiểm tra qua Validator."""
    req = normalized_request
    if crowd_analysis.get("data_revision") != DATA_REVISION:
        return {
            "plan_result_id": "res_revision_mismatch",
            "crowd_analysis_id": crowd_analysis.get("analysis_id", ""),
            "scenario_id": scenario_id,
            "data_revision": DATA_REVISION,
            "status": "failed",
            "plans": [],
            "unfeasible_reasons": [],
            "warnings": [],
            "errors": ["Crowd analysis không thuộc Google Places V2."],
        }
    hard = req.get("hard_constraints", {})
    prefs = req.get("preferences", {})
    num_plans = req.get("number_of_plans", 2)
    members = req.get("group_members", [])
    ticket_groups = req.get("ticket_groups") or members_to_ticket_groups(members)
    entry_ticket = calculate_entry_ticket(ticket_groups, req.get("start_at", "2026-09-18T14:00:00+07:00"))

    start_node = req.get("start_node_id", START_NODE_ID)
    end_node = req.get("end_node_id", START_NODE_ID)
    if start_node == "start_sea_hub":
        start_node = START_NODE_ID
    if end_node == "start_sea_hub":
        end_node = START_NODE_ID
    start_time = datetime.fromisoformat(req.get("start_at", "2026-09-18T14:00:00+07:00"))
    deadline = datetime.fromisoformat(req.get("end_by", "2026-09-18T16:00:00+07:00"))
    total_window_minutes = (deadline - start_time).total_seconds() / 60

    indoor_only = hard.get("indoor_only", False)
    max_thrill = hard.get("max_thrill_level", "moderate")
    max_wait = hard.get("max_wait_minutes_per_stop", 20)
    budget_total = hard.get("budget_vnd_total")
    min_buffer = hard.get("min_end_buffer_minutes", 10)
    crowd_items = {item["service_id"]: item for item in crowd_analysis.get("items", [])}
    crowd_data_available = any(
        item.get("data_quality") != "unavailable" and item.get("wait_minutes") is not None
        for item in crowd_items.values()
    )
    allow_unknown = hard.get("allow_unknown_crowd", True) or not crowd_data_available
    min_act = hard.get("min_activity_count", 3)
    excluded = set(hard.get("excluded_service_ids", []))

    # 1. Gọi MCP lấy danh mục và ma trận đường đi
    analyzed_service_ids = [item["service_id"] for item in crowd_analysis.get("items", [])]
    attractions_list = call_mcp_tool("get_attractions", {
        "scenario_id": scenario_id,
        "service_ids": analyzed_service_ids or None,
    })
    if any(attraction.get("data_revision") != DATA_REVISION for attraction in attractions_list):
        return {
            "plan_result_id": "res_revision_mismatch",
            "crowd_analysis_id": crowd_analysis.get("analysis_id", ""),
            "scenario_id": scenario_id,
            "data_revision": DATA_REVISION,
            "status": "failed",
            "plans": [],
            "unfeasible_reasons": [],
            "warnings": [],
            "errors": ["MCP catalog không thuộc Google Places V2."],
        }
    attractions_map = {a["service_id"]: a for a in attractions_list}

    weather_data = call_mcp_tool("get_weather", {"start_at": req.get("start_at"), "end_by": req.get("end_by")})
    weather_windows = weather_data.get("weather_windows", [])

    # 2. Lọc điểm ban đầu
    eligible_sids = []
    unfeasible_reasons = []

    for sid, attr in attractions_map.items():
        if sid in excluded:
            continue
        c_item = crowd_items.get(sid, {})

        # Trạng thái vận hành
        if c_item.get("operating_status") == "temporarily_closed":
            continue

        # Giới hạn trong nhà
        if indoor_only and not attr.get("indoor", False):
            continue

        # Giới hạn cảm giác mạnh
        thrill = attr.get("thrill_level", "none")
        if THRILL_ORDER.get(thrill, 0) > THRILL_ORDER.get(max_thrill, 2):
            continue

        # Giới hạn chờ
        wait_min = c_item.get("wait_minutes")
        if wait_min is None:
            if not allow_unknown:
                continue
            wait_min = 0
        elif wait_min > max_wait:
            continue

        # Lịch mở cửa
        sched = attr.get("schedule", {})
        if sched.get("mode") == "scheduled":
            # Kiểm tra suất diễn có nằm trong khung giờ
            session_times = sched.get("session_start_times", [])
            has_valid_session = False
            for st_str in session_times:
                st = datetime.fromisoformat(st_str)
                if start_time <= st < deadline:
                    has_valid_session = True
                    break
            if not has_valid_session:
                continue

        # Kiểm tra thành viên
        eligible, _ = is_eligible_for_group(attr, members)
        if not eligible:
            continue

        eligible_sids.append(sid)

    category_priority = {"ride": 0, "attraction": 1, "food": 2, "service": 3, "shop": 4, "hotel": 5}
    if prefs.get("meal_required"):
        category_priority["food"] = 0
    eligible_sids.sort(key=lambda sid: (
        category_priority.get(attractions_map[sid].get("category"), 9),
        -(attractions_map[sid].get("rating") or 0),
        -(attractions_map[sid].get("reviews_count") or 0),
    ))
    eligible_sids = eligible_sids[:MAX_PLANNING_CANDIDATES]

    if len(eligible_sids) < min_act:
        return {
            "plan_result_id": "res_none",
            "crowd_analysis_id": crowd_analysis.get("analysis_id", ""),
            "scenario_id": scenario_id,
            "data_revision": DATA_REVISION,
            "status": "no_feasible_plan",
            "plans": [],
            "unfeasible_reasons": [
                f"Chỉ có {len(eligible_sids)} điểm thỏa mãn các tiêu chí (yêu cầu tối thiểu {min_act} điểm).",
                f"Các ràng buộc giới hạn: trong nhà={indoor_only}, chờ tối đa={max_wait}p, cảm giác mạnh={max_thrill}.",
            ],
            "warnings": [],
        }

    all_nodes = [attractions_map[sid]["location"]["node_id"] for sid in eligible_sids] + [start_node, end_node]
    route_data = call_mcp_tool("get_route_matrix", {"node_ids": list(set(all_nodes))})
    routes = route_data.get("matrix", {})

    # 3. Tìm kiếm các tổ hợp khả thi (L3: giới hạn iterations chống DoS)
    candidate_plans = []
    # Thử độ dài từ min_act đến min(min_act + 2, len(eligible_sids))
    max_len = min(min_act + 1, len(eligible_sids))
    search_count = 0
    search_exhausted = False
    for r in range(min_act, max_len + 1):
        if search_exhausted:
            break
        for seq in itertools.permutations(eligible_sids, r):
            search_count += 1
            if search_count > MAX_SEARCH_ITERATIONS:
                logger.warning(
                    "L3: Search iteration limit reached (%d). Stopping permutation search.",
                    MAX_SEARCH_ITERATIONS,
                )
                search_exhausted = True
                break
            curr_time = start_time
            curr_node = start_node
            legs = []
            total_cost = entry_ticket["total_vnd"]
            feasible = True

            for step_idx, sid in enumerate(seq, 1):
                attr = attractions_map[sid]
                c_item = crowd_items.get(sid, {})
                dest_node = attr["location"]["node_id"]

                # Thời gian đi bộ
                walk_min = routes.get(curr_node, {}).get(dest_node, {}).get("walking_minutes")
                if walk_min is None:
                    feasible = False
                    break
                arrival = curr_time + timedelta(minutes=walk_min)

                sched = attr.get("schedule", {})
                mode = sched.get("mode", "walk_in")
                dur_min = sched.get("visit_duration_minutes", 15)

                if mode == "walk_in":
                    wait_min = c_item.get("wait_minutes") or 0
                    act_start = arrival + timedelta(minutes=wait_min)
                    act_end = act_start + timedelta(minutes=dur_min)
                else:
                    # Suất diễn định giờ (Show)
                    checkin_buf = sched.get("check_in_buffer_minutes", 5)
                    # Chọn suất đầu tiên sau khi đến
                    session_times = [
                        datetime.fromisoformat(st) for st in sched.get("session_start_times", [])
                        if datetime.fromisoformat(st) >= arrival + timedelta(minutes=checkin_buf)
                    ]
                    if not session_times:
                        feasible = False
                        break
                    act_start = session_times[0]
                    wait_min = int((act_start - arrival).total_seconds() / 60)
                    act_end = act_start + timedelta(minutes=dur_min)

                if not is_open_for_visit(sched, act_start, act_end):
                    feasible = False
                    break

                if act_end > deadline:
                    feasible = False
                    break

                # Chi phí
                step_cost = 0
                attr_loc = attr.get("location") or {}

                legs.append({
                    "step": step_idx,
                    "service_id": sid,
                    "service_name": attr.get("name", sid),
                    "node_id": dest_node,
                    "lat": attr_loc.get("lat"),
                    "lng": attr_loc.get("lng"),
                    "arrival_time": arrival.strftime("%H:%M"),
                    "start_time": act_start.strftime("%H:%M"),
                    "end_time": act_end.strftime("%H:%M"),
                    "walk_from_prev_minutes": walk_min,
                    "wait_minutes": wait_min,
                    "activity_duration_minutes": dur_min,
                    "cost_vnd": step_cost,
                    "indoor": attr.get("indoor", False),
                    "note": f"Hàng chờ {wait_min}p, trải nghiệm {dur_min}p; đã bao gồm trong vé cổng",
                })

                curr_time = act_end
                curr_node = dest_node

            if not feasible:
                continue

            # Đi bộ về điểm kết thúc
            return_walk = routes.get(curr_node, {}).get(end_node, {}).get("walking_minutes")
            if return_walk is None:
                continue
            final_arrival = curr_time + timedelta(minutes=return_walk)
            if final_arrival > deadline:
                continue

            buffer_min = int((deadline - final_arrival).total_seconds() / 60)
            if buffer_min < min_buffer:
                continue

            total_dur = int((final_arrival - start_time).total_seconds() / 60)

            # Tính điểm phong cách
            total_wait = sum(leg["wait_minutes"] for leg in legs)
            rides_count = sum(1 for sid in seq if attractions_map[sid].get("category") == "ride")
            indoor_count = sum(1 for sid in seq if attractions_map[sid].get("indoor", False))

            plan_candidate = {
                "sequence": list(seq),
                "legs": legs,
                "total_duration_minutes": total_dur,
                "end_buffer_minutes": buffer_min,
                "total_cost_vnd": total_cost,
                "cost_breakdown": {"entry_ticket": entry_ticket, "addons_vnd": 0},
                "start_node_id": start_node,
                "end_node_id": end_node,
                "return_arrival_time": final_arrival.strftime("%H:%M"),
                "total_wait": total_wait,
                "rides_count": rides_count,
                "indoor_count": indoor_count,
            }
            candidate_plans.append(plan_candidate)

    if not candidate_plans:
        return {
            "plan_result_id": "res_none",
            "crowd_analysis_id": crowd_analysis.get("analysis_id", ""),
            "scenario_id": scenario_id,
            "data_revision": DATA_REVISION,
            "status": "no_feasible_plan",
            "plans": [],
            "unfeasible_reasons": [
                f"Không tìm được lộ trình nào hoàn thành trước {deadline.strftime('%H:%M')} với thời gian dự phòng ≥{min_buffer} phút.",
                "Vui lòng tăng khung giờ chơi hoặc giảm số lượng điểm tối thiểu.",
            ],
            "warnings": [],
        }

    # 4. Phân loại 2 phong cách khác nhau: Gentle vs More Rides
    # Gentle: ưu tiên tổng thời gian chờ thấp nhất, đệm dự phòng cao, thư thái
    # More Rides: ưu tiên số trò chơi (ride) nhiều nhất, đa dạng
    candidate_plans.sort(key=lambda p: (p["total_wait"], -p["end_buffer_minutes"]))
    gentle_raw = candidate_plans[0]

    # Tìm phương án 2 (More rides) khác ít nhất 1 điểm hoạt động có ý nghĩa
    more_rides_raw = None
    gentle_set = set(gentle_raw["sequence"])

    # Sắp xếp theo số rides giảm dần, sau đó đến wait
    by_rides = sorted(candidate_plans, key=lambda p: (-p["rides_count"], p["total_wait"]))
    for p in by_rides:
        p_set = set(p["sequence"])
        if p_set != gentle_set and len(p_set - gentle_set) >= 1:
            more_rides_raw = p
            break

    selected_raw = [("gentle", "Phương án 1: Nhẹ nhàng, ít chờ", gentle_raw)]
    if num_plans >= 2:
        if more_rides_raw:
            selected_raw.append(("more_rides", "Phương án 2: Nhiều trò chơi trải nghiệm", more_rides_raw))
        elif len(candidate_plans) > 1:
            # Nếu không tìm thấy tập hoàn toàn khác nhưng có thứ tự khác hoặc biến thể
            selected_raw.append(("more_rides", "Phương án 2: Lộ trình thay thế", candidate_plans[1]))

    # 5. Chạy Validator xác thực từng phương án
    validated_plans = []
    for idx, (style, label, raw) in enumerate(selected_raw, 1):
        fallback_rationale = (
            f"{label}: Tổng thời gian {raw['total_duration_minutes']} phút, dự phòng {raw['end_buffer_minutes']} phút trước 16:00. "
            f"Đi qua {len(raw['sequence'])} điểm ({', '.join(attractions_map[s]['name'] for s in raw['sequence'])}), "
            f"thời gian chờ tích lũy chỉ {raw['total_wait']} phút; các điểm chơi đã bao gồm trong vé cổng."
        )
        plan_rationale = fallback_rationale
        if is_llm_available():
            try:
                llm_rationale = generate_plan_rationale_with_llm(
                    style_label=label,
                    legs=raw["legs"],
                    group_members=members,
                    total_wait=raw["total_wait"],
                    buffer_min=raw["end_buffer_minutes"],
                    total_cost=raw["total_cost_vnd"],
                )
                if llm_rationale:
                    plan_rationale = llm_rationale
            except Exception as e:
                logger.warning("LLM rationale generation error: %s", e)

        plan_stops = [
            {
                "name": leg["service_name"],
                "lat": leg["lat"],
                "lng": leg["lng"],
                "time": leg["arrival_time"],
                "duration_minutes": leg["activity_duration_minutes"],
                "note": leg["note"],
            }
            for leg in raw["legs"]
            if leg.get("lat") is not None and leg.get("lng") is not None
        ]

        plan_obj = {
            "plan_id": f"plan_opt_{idx}_{style}",
            "style": style,
            "style_label": label,
            "total_duration_minutes": raw["total_duration_minutes"],
            "end_buffer_minutes": raw["end_buffer_minutes"],
            "total_cost_vnd": raw["total_cost_vnd"],
            "cost_breakdown": raw["cost_breakdown"],
            "start_node_id": raw["start_node_id"],
            "end_node_id": raw["end_node_id"],
            "return_arrival_time": raw["return_arrival_time"],
            "legs": raw["legs"],
            "stops": plan_stops,
            "travel_mode": "walking",
            "service_ids": raw["sequence"],
            "rationale": plan_rationale,
        }


        is_valid, violations = validate_plan(plan_obj, req, attractions_map, crowd_items, weather_windows)
        plan_obj["is_feasible"] = is_valid
        plan_obj["constraint_report"] = {
            "is_valid": is_valid,
            "violations": violations,
        }
        if is_valid:
            validated_plans.append(plan_obj)

    if not validated_plans:
        return {
            "plan_result_id": "res_failed_validation",
            "crowd_analysis_id": crowd_analysis.get("analysis_id", ""),
            "scenario_id": scenario_id,
            "data_revision": DATA_REVISION,
            "status": "no_feasible_plan",
            "plans": [],
            "unfeasible_reasons": ["Tất cả các phương án sinh ra đều không vượt qua bộ kiểm tra ràng buộc (Validator)."],
            "warnings": [],
        }

    return {
        "plan_result_id": "res_success",
        "crowd_analysis_id": crowd_analysis.get("analysis_id", ""),
        "scenario_id": scenario_id,
        "data_revision": DATA_REVISION,
        "status": "completed",
        "plans": validated_plans,
        "unfeasible_reasons": [],
        "warnings": [],
    }


# --- Logic Lập Lịch Trình Du Lịch Tổng Quát & Bản Đồ Số (Agent A1) ---

SYSTEM_PROMPT_ITINERARY = """Bạn là một trợ lý lập kế hoạch du lịch. Nhiệm vụ của bạn là tạo lịch trình chi tiết cho chuyến đi dựa trên yêu cầu của người dùng, và xuất kết quả dưới dạng JSON để hệ thống có thể hiển thị lên bản đồ trực quan kèm chỉ đường.

ĐẦU VÀO bạn sẽ nhận được:
- Điểm đến / khu vực (ví dụ: Hà Nội, Đà Lạt...)
- Số ngày
- Sở thích hoặc loại hình (tham quan, ẩm thực, nghỉ dưỡng...)
- Phương tiện di chuyển (đi bộ / xe máy / ô tô)
- (Tùy chọn) ngân sách, số người

YÊU CẦU KHI LẬP LỊCH TRÌNH:
1. Chọn các địa điểm cụ thể, có thật, theo đúng khu vực yêu cầu — không bịa tên địa điểm.
2. Với MỖI địa điểm, PHẢI cung cấp toạ độ (lat, lng) chính xác. Nếu không chắc chắn toạ độ, hãy dùng tên địa điểm đầy đủ và rõ ràng nhất có thể để hệ thống geocode sau.
3. Sắp xếp các điểm theo thứ tự di chuyển hợp lý về mặt địa lý (tránh đi vòng lại), có tính đến giờ mở cửa nếu có thông tin.
4. Ước lượng thời gian nên dành ở mỗi điểm.
5. Nếu chuyến đi nhiều ngày, chia rõ theo từng ngày.

ĐỊNH DẠNG ĐẦU RA — CHỈ trả về JSON theo đúng cấu trúc sau, không thêm text giải thích nào khác ngoài JSON:

{
  "trip_title": "Tên chuyến đi",
  "travel_mode": "driving" | "walking" | "cycling",
  "days": [
    {
      "day_label": "Ngày 1",
      "stops": [
        {
          "name": "Tên địa điểm",
          "lat": 21.0285,
          "lng": 105.8524,
          "time": "08:00",
          "duration_minutes": 60,
          "note": "Mô tả ngắn hoặc lý do nên ghé"
        }
      ]
    }
  ]
}

LƯU Ý:
- Mỗi ngày nên có 3–6 điểm dừng để lịch trình không quá dày hoặc quá thưa.
- "travel_mode" phải khớp với phương tiện người dùng chọn, vì hệ thống bản đồ sẽ dùng giá trị này để tính tuyến đường và chỉ dẫn phù hợp (ô tô/xe máy dùng "driving", đi bộ dùng "walking").
- Nếu người dùng không nêu rõ phương tiện, mặc định chọn "driving".
- Không trả lời bằng markdown code block (không bọc ```), chỉ trả về JSON thuần để hệ thống parse trực tiếp."""


class TripPlanRequest(BaseModel):
    destination: str = Field(..., description="Điểm đến hoặc khu vực, ví dụ: Đà Lạt, Hà Nội, Nha Trang...")
    days: int = Field(default=1, ge=1, le=7, description="Số ngày chuyến đi")
    preferences: str = Field(default="tham quan, ẩm thực", description="Sở thích hoặc loại hình chuyến đi")
    travel_mode: str = Field(default="driving", description="driving | walking | cycling")
    budget: str | None = Field(default=None, description="Ngân sách dự kiến")
    people: int | None = Field(default=2, description="Số lượng thành viên trong đoàn")


FALLBACK_SAMPLES: dict[str, dict[str, Any]] = {
    "nha trang": {
        "trip_title": "Khám Phá VinWonders & Vịnh Biển Nha Trang",
        "travel_mode": "driving",
        "days": [
            {
                "day_label": "Ngày 1",
                "stops": [
                    {
                        "name": "Ga Cáp Treo VinWonders Nha Trang",
                        "lat": 12.2023,
                        "lng": 109.2178,
                        "time": "08:30",
                        "duration_minutes": 45,
                        "note": "Đi cáp treo vượt biển ngắm toàn cảnh vịnh Nha Trang sang đảo Hòn Tre",
                    },
                    {
                        "name": "Thủy Cung VinWonders Nha Trang (Cung Điện Hải Vương)",
                        "lat": 12.2172,
                        "lng": 109.2415,
                        "time": "09:30",
                        "duration_minutes": 90,
                        "note": "Khám phá đường hầm sinh vật biển và xem biểu diễn nàng tiên cá",
                    },
                    {
                        "name": "Khu Trò Chơi Cảm Giác Mạnh VinWonders",
                        "lat": 12.2185,
                        "lng": 109.2428,
                        "time": "11:15",
                        "duration_minutes": 75,
                        "note": "Trải nghiệm đu quay lộn đầu và tàu lượn siêu tốc mạo hiểm",
                    },
                    {
                        "name": "Nhà Hàng Ẩm Thực VinWonders",
                        "lat": 12.2168,
                        "lng": 109.2405,
                        "time": "12:45",
                        "duration_minutes": 60,
                        "note": "Nghỉ trưa và thưởng thức ẩm thực đặc sắc",
                    },
                    {
                        "name": "Công Viên Nước VinWonders Nha Trang",
                        "lat": 12.2155,
                        "lng": 109.2435,
                        "time": "14:00",
                        "duration_minutes": 120,
                        "note": "Vui chơi tại vịnh phao nổi và hệ thống máng trượt nước hiện đại",
                    },
                    {
                        "name": "Quảng Trường Thần Thoại - Tata Show",
                        "lat": 12.2178,
                        "lng": 109.2412,
                        "time": "19:15",
                        "duration_minutes": 60,
                        "note": "Thưởng thức siêu phẩm trình diễn đa phương tiện thực cảnh hoành tráng",
                    },
                ],
            }
        ],
    },
    "đà lạt": {
        "trip_title": "Hành Trình Mộng Mơ Đà Lạt 2 Ngày",
        "travel_mode": "driving",
        "days": [
            {
                "day_label": "Ngày 1",
                "stops": [
                    {
                        "name": "Hồ Xuân Hương",
                        "lat": 11.9404,
                        "lng": 108.4452,
                        "time": "07:30",
                        "duration_minutes": 45,
                        "note": "Dạo quanh hồ hít thở không khí se lạnh buổi sớm và ngắm bình minh",
                    },
                    {
                        "name": "Ga Đà Lạt",
                        "lat": 11.9416,
                        "lng": 108.4552,
                        "time": "08:30",
                        "duration_minutes": 60,
                        "note": "Nhà ga cổ kính nhất Đông Dương mang phong cách kiến trúc Pháp độc đáo",
                    },
                    {
                        "name": "Vườn Hoa Thành Phố Đà Lạt",
                        "lat": 11.9515,
                        "lng": 108.4526,
                        "time": "10:00",
                        "duration_minutes": 90,
                        "note": "Chiêm ngưỡng hàng trăm loài hoa ôn đới rực rỡ sắc màu",
                    },
                    {
                        "name": "Quán Bánh Căn Lệ",
                        "lat": 11.9362,
                        "lng": 108.4385,
                        "time": "12:00",
                        "duration_minutes": 60,
                        "note": "Thưởng thức món bánh căn trứng cút xíu mại trứ danh Đà Lạt",
                    },
                    {
                        "name": "Chùa Linh Phước (Chùa Ve Chai)",
                        "lat": 11.9238,
                        "lng": 108.4988,
                        "time": "14:00",
                        "duration_minutes": 90,
                        "note": "Công trình Phật giáo kỳ vĩ khảm từ hàng triệu mảnh gốm sành sứ",
                    },
                    {
                        "name": "Chợ Đêm Đà Lạt",
                        "lat": 11.9429,
                        "lng": 108.4371,
                        "time": "18:30",
                        "duration_minutes": 120,
                        "note": "Thưởng thức bánh tráng nướng, sữa đậu nành nóng và mua đặc sản",
                    },
                ],
            },
            {
                "day_label": "Ngày 2",
                "stops": [
                    {
                        "name": "Đồi Chè Cầu Đất",
                        "lat": 11.8596,
                        "lng": 108.5714,
                        "time": "06:00",
                        "duration_minutes": 120,
                        "note": "Săn mây sớm và ngắm những nương chè xanh ngát bạt ngàn",
                    },
                    {
                        "name": "Dinh I Bảo Đại",
                        "lat": 11.9287,
                        "lng": 108.4682,
                        "time": "09:30",
                        "duration_minutes": 75,
                        "note": "Dinh thự sang trọng giữa rừng thông cổ thụ của vị vua cuối cùng",
                    },
                    {
                        "name": "Thác Datanla",
                        "lat": 11.9029,
                        "lng": 108.4485,
                        "time": "11:30",
                        "duration_minutes": 105,
                        "note": "Trải nghiệm hệ thống xe trượt máng Alpine Coaster xuyên rừng thông mạo hiểm",
                    },
                    {
                        "name": "Hồ Tuyền Lâm & Thiền Viện Trúc Lâm",
                        "lat": 11.9042,
                        "lng": 108.4354,
                        "time": "14:30",
                        "duration_minutes": 90,
                        "note": "Không gian thanh tịnh tĩnh lặng bên hồ nước trong xanh",
                    },
                ],
            },
        ],
    },
    "hà nội": {
        "trip_title": "Dạo Bước Hà Nội Nghìn Năm Văn Hiến",
        "travel_mode": "walking",
        "days": [
            {
                "day_label": "Ngày 1",
                "stops": [
                    {
                        "name": "Hồ Hoàn Kiếm & Đền Ngọc Sơn",
                        "lat": 21.0307,
                        "lng": 105.8524,
                        "time": "08:00",
                        "duration_minutes": 60,
                        "note": "Đi dạo quanh bờ hồ, ngắm Tháp Rùa và cầu Thê Húc đỏ son",
                    },
                    {
                        "name": "Phố Cổ Hà Nội (Hàng Gai, Hàng Bạc, Hàng Đào)",
                        "lat": 21.0345,
                        "lng": 105.8501,
                        "time": "09:15",
                        "duration_minutes": 75,
                        "note": "Khám phá nét kiến trúc nhà ống cổ và các làng nghề truyền thống",
                    },
                    {
                        "name": "Phở Bát Đàn",
                        "lat": 21.0336,
                        "lng": 105.8465,
                        "time": "10:45",
                        "duration_minutes": 45,
                        "note": "Thưởng thức bát phở bò truyền thống nước dùng thơm ngọt ngào",
                    },
                    {
                        "name": "Văn Miếu - Quốc Tử Giám",
                        "lat": 21.0285,
                        "lng": 105.8355,
                        "time": "12:00",
                        "duration_minutes": 90,
                        "note": "Trường đại học đầu tiên của Việt Nam với 82 bia Tiến sĩ vinh danh hiền tài",
                    },
                    {
                        "name": "Nhà Thờ Lớn Hà Nội",
                        "lat": 21.0288,
                        "lng": 105.8495,
                        "time": "14:30",
                        "duration_minutes": 45,
                        "note": "Kiến trúc Gothic cổ kính và thưởng thức trà chanh vỉa hè",
                    },
                ],
            }
        ],
    },
}


def _clean_json_string(text: str) -> str:
    """Làm sạch chuỗi JSON nếu LLM vô tình bọc trong markdown code block."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()


def _validate_itinerary_structure(data: dict[str, Any]) -> bool:
    """Kiểm tra cấu trúc JSON đúng chuẩn schema yêu cầu."""
    if not isinstance(data, dict):
        return False
    if "trip_title" not in data or "travel_mode" not in data or "days" not in data:
        return False
    if not isinstance(data["days"], list) or len(data["days"]) == 0:
        return False
    for day in data["days"]:
        if "stops" not in day or not isinstance(day["stops"], list):
            return False
        for stop in day["stops"]:
            if not all(k in stop for k in ("name", "lat", "lng", "time", "duration_minutes", "note")):
                return False
            try:
                lat = float(stop["lat"])
                lng = float(stop["lng"])
                if lat < 0:
                    lat = abs(lat)
                if lng < 0:
                    lng = abs(lng)
                stop["lat"] = round(lat, 5)
                stop["lng"] = round(lng, 5)
            except (ValueError, TypeError):
                return False
    return True


def get_fallback_itinerary(dest: str, days: int, mode: str) -> dict[str, Any]:
    """Tạo lịch trình fallback chất lượng cao khi không có LLM."""
    dest_lower = dest.lower().strip()
    for key, sample in FALLBACK_SAMPLES.items():
        if key in dest_lower or dest_lower in key:
            plan = json.loads(json.dumps(sample))
            plan["travel_mode"] = mode if mode in ("driving", "walking", "cycling") else "driving"
            if days == 1 and len(plan["days"]) > 1:
                plan["days"] = plan["days"][:1]
            return plan

    # Mẫu mặc định cho bất kỳ địa điểm nào khác
    return {
        "trip_title": f"Hành Trình Khám Phá {dest.title()}",
        "travel_mode": mode if mode in ("driving", "walking", "cycling") else "driving",
        "days": [
            {
                "day_label": f"Ngày {i + 1}",
                "stops": [
                    {
                        "name": f"Điểm tham quan trung tâm {dest.title()} (Chặng 1)",
                        "lat": 12.2388 + (i * 0.01),
                        "lng": 109.1967 + (i * 0.01),
                        "time": "08:30",
                        "duration_minutes": 90,
                        "note": "Khám phá danh thắng nổi tiếng và chụp hình lưu niệm",
                    },
                    {
                        "name": f"Khu ẩm thực & đặc sản {dest.title()} (Chặng 2)",
                        "lat": 12.2420 + (i * 0.01),
                        "lng": 109.1980 + (i * 0.01),
                        "time": "11:30",
                        "duration_minutes": 60,
                        "note": "Thưởng thức các món ngon truyền thống trứ danh địa phương",
                    },
                    {
                        "name": f"Khu vui chơi & thư giãn {dest.title()} (Chặng 3)",
                        "lat": 12.2450 + (i * 0.01),
                        "lng": 109.2020 + (i * 0.01),
                        "time": "14:00",
                        "duration_minutes": 120,
                        "note": "Trải nghiệm hoạt động giải trí và ngắm hoàng hôn",
                    },
                    {
                        "name": f"Chợ đêm & phố đi bộ {dest.title()} (Chặng 4)",
                        "lat": 12.2405 + (i * 0.01),
                        "lng": 109.1950 + (i * 0.01),
                        "time": "18:30",
                        "duration_minutes": 90,
                        "note": "Dạo phố đêm, mua quà lưu niệm và ngắm cảnh đêm rực rỡ",
                    },
                ],
            }
            for i in range(min(days, 5))
        ],
    }


def generate_trip_itinerary(req: TripPlanRequest) -> dict[str, Any]:
    """Tạo lịch trình du lịch chi tiết xuất JSON theo đúng format yêu cầu."""
    mode = req.travel_mode if req.travel_mode in ("driving", "walking", "cycling") else "driving"
    user_prompt = (
        f"Lập lịch trình du lịch chi tiết theo các thông tin sau:\n"
        f"- Điểm đến / khu vực: {req.destination}\n"
        f"- Số ngày: {req.days} ngày\n"
        f"- Sở thích / loại hình: {req.preferences}\n"
        f"- Phương tiện di chuyển: {mode}\n"
    )
    if req.budget:
        user_prompt += f"- Ngân sách dự kiến: {req.budget}\n"
    if req.people:
        user_prompt += f"- Số lượng người: {req.people} người\n"

    user_prompt += (
        "\nYêu cầu đặc biệt: CHỈ trả về duy nhất chuỗi JSON thuần hợp lệ theo đúng cấu trúc schema, "
        "tuyệt đối không bọc trong ```json và không có văn bản giải thích nào khác."
    )

    if not is_llm_available():
        logger.info("LLM không khả dụng, sử dụng bộ dữ liệu mẫu GPS cho %s", req.destination)
        return get_fallback_itinerary(req.destination, req.days, mode)

    try:
        raw_response = call_llm(prompt=user_prompt, system_instruction=SYSTEM_PROMPT_ITINERARY)
        if not raw_response:
            logger.warning("LLM trả về rỗng, chuyển sang fallback")
            return get_fallback_itinerary(req.destination, req.days, mode)

        cleaned = _clean_json_string(raw_response)
        parsed = json.loads(cleaned)

        if _validate_itinerary_structure(parsed):
            if parsed.get("travel_mode") not in ("driving", "walking", "cycling"):
                parsed["travel_mode"] = mode
            return parsed
        else:
            logger.warning("Cấu trúc JSON từ LLM không khớp schema, chuyển sang fallback")
            return get_fallback_itinerary(req.destination, req.days, mode)

    except Exception as err:
        logger.error("Lỗi tạo lịch trình du lịch từ LLM: %s", err)
        return get_fallback_itinerary(req.destination, req.days, mode)


def plan_trip_itinerary_logic(req: TripPlanRequest | dict[str, Any]) -> dict[str, Any]:
    """Logic lập lịch trình du lịch tổng quát có toạ độ GPS xuất JSON do Agent A1 phụ trách."""
    if isinstance(req, dict):
        req = TripPlanRequest(**req)
    return generate_trip_itinerary(req)


# --- A2A Server & Executor ---

class PlannerSpecialistExecutor(AgentExecutor):
    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        raw_text = ""
        if context.message and context.message.parts:
            raw_text = context.message.parts[0].text

        try:
            req_data = json.loads(raw_text) if raw_text else {}
        except Exception:
            req_data = {}

        session_id = req_data.get("session_id", "default_session")
        turn_id = req_data.get("turn_id", "turn_001")
        request_id = req_data.get("request_id", "req_a1_001")
        scenario_id = req_data.get("scenario_id", "base")
        action = req_data.get("action", "create_plans")
        inp = req_data.get("input", {})

        # Nhánh 1: Lập lịch trình du lịch tổng quát & bản đồ GPS
        if action == "plan_trip_itinerary":
            trip_req_data = inp.get("trip_request", inp)
            trip_result = plan_trip_itinerary_logic(trip_req_data)
            agent_result = {
                "schema_version": "1.0",
                "session_id": session_id,
                "turn_id": turn_id,
                "request_id": request_id,
                "action": "plan_trip_itinerary",
                "status": "completed",
                "data_revision": req_data.get("data_revision", DATA_REVISION),
                "result": trip_result,
                "warnings": [],
                "errors": [],
            }
            reply_msg = Message(
                role=Role.assistant,
                parts=[TextPart(text=json.dumps(agent_result, ensure_ascii=False))],
            )
            await event_queue.enqueue_event(reply_msg)
            return

        # Nhánh 2: Lập lịch trình chi tiết khu vui chơi VinWonders
        normalized_request = inp.get("normalized_request", {})
        crowd_analysis = inp.get("crowd_analysis", {})

        plan_result = plan_itinerary_logic(
            normalized_request=normalized_request,
            crowd_analysis=crowd_analysis,
            scenario_id=scenario_id,
        )

        agent_result = {
            "schema_version": "1.0",
            "session_id": session_id,
            "turn_id": turn_id,
            "request_id": request_id,
            "action": "create_plans",
            "status": plan_result.get("status", "completed"),
            "input_memory_version": req_data.get("memory_ref", {}).get("version", 1),
            "data_revision": req_data.get("data_revision", DATA_REVISION),
            "result": plan_result,
            "warnings": plan_result.get("warnings", []),
            "errors": plan_result.get("unfeasible_reasons", []),
        }

        reply_msg = Message(
            role=Role.assistant,
            parts=[TextPart(text=json.dumps(agent_result, ensure_ascii=False))],
        )
        await event_queue.enqueue_event(reply_msg)

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        pass


agent_card = AgentCard(
    name="a1_planner_specialist",
    description="Agent chuyên gia lập lịch trình, tối ưu đường đi và bản đồ toạ độ GPS cho du lịch & vui chơi",
    version="1.1.0",
    url="http://127.0.0.1:8001",
    capabilities=AgentCapabilities(),
    default_input_modes=["text"],
    default_output_modes=["text"],
    skills=[
        AgentSkill(
            id="create_plans",
            name="Lập lịch trình khu vui chơi",
            description="Tạo và xác thực 1-2 phương án lịch trình vui chơi theo thời gian thực",
            tags=["planner", "routing", "scheduling"],
        ),
        AgentSkill(
            id="plan_trip_itinerary",
            name="Lập lịch trình du lịch & Bản đồ GPS",
            description="Lập lịch trình chi tiết theo điểm đến, số ngày, toạ độ GPS chính xác và thứ tự tối ưu xuất JSON bản đồ",
            tags=["trip_planner", "map", "gps", "routing"],
        ),
    ],
)

handler = DefaultRequestHandler(
    agent_executor=PlannerSpecialistExecutor(),
    task_store=InMemoryTaskStore(),
)

app_builder = A2AFastAPIApplication(agent_card=agent_card, http_handler=handler)
app = app_builder.build()


@app.get("/health")
def health() -> dict[str, Any]:
    return {"status": "ok", "service": "v_ai_internal", "port": "8001", "data_revision": DATA_REVISION}


class DirectPlanRequest(BaseModel):
    normalized_request: dict[str, Any]
    crowd_analysis: dict[str, Any]
    scenario_id: str = "base"


@app.post("/api/plan", dependencies=[Depends(require_internal_secret)])
def direct_plan(req: DirectPlanRequest) -> dict[str, Any]:
    return plan_itinerary_logic(req.normalized_request, req.crowd_analysis, req.scenario_id)


@app.post("/api/itinerary/plan")
def a1_itinerary_plan(req: TripPlanRequest) -> dict[str, Any]:
    """Endpoint lập lịch trình du lịch tổng quát & bản đồ GPS do Agent A1 phụ trách."""
    plan = plan_trip_itinerary_logic(req)
    return {"status": "success", "data": plan}


@app.get("/api/itinerary/samples")
def a1_itinerary_samples() -> dict[str, Any]:
    """Danh sách mẫu lịch trình GPS có sẵn của Agent A1."""
    return {"status": "success", "samples": FALLBACK_SAMPLES}


if __name__ == "__main__":
    print("Khởi động Agent A1 (Planner Specialist) tại http://127.0.0.1:8001...")
    uvicorn.run(app, host="127.0.0.1", port=8001, log_level="info")
