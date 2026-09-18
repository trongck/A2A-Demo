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
from typing import Any

import httpx
from pydantic import BaseModel
import uvicorn

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
from shared.llm import (
    generate_plan_rationale_with_llm,
    generate_unfeasible_explanation_with_llm,
    get_llm_status,
    is_llm_available,
)

MCP_URL = "http://127.0.0.1:8003"



def call_mcp_tool(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Gọi công cụ qua MCP Server HTTP endpoint với caller_agent=a1_planner_specialist."""
    try:
        with httpx.Client(timeout=3.0) as client:
            resp = client.post(
                f"{MCP_URL}/api/tools/call",
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
        return tool_get_attractions(arguments.get("scenario_id", "base"), arguments.get("service_ids"))
    elif tool_name == "get_crowd_snapshots":
        return tool_get_crowd_snapshots(arguments.get("scenario_id", "base"), arguments.get("service_ids"))
    elif tool_name == "get_route_matrix":
        return tool_get_route_matrix(arguments.get("node_ids", []))
    elif tool_name == "get_weather":
        return tool_get_weather(arguments.get("start_at", ""), arguments.get("end_by", ""))
    return {}


# --- Bảng chuyển đổi cấp độ cảm giác mạnh ---
THRILL_ORDER = {"none": 0, "low": 1, "moderate": 2, "high": 3, "extreme": 4}


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
    budget_total = hard.get("budget_vnd_total", 150000)
    min_buffer = hard.get("min_end_buffer_minutes", 10)
    min_act = hard.get("min_activity_count", 3)
    members = req.get("group_members", [])

    legs = plan.get("legs", [])
    if len(legs) < min_act:
        violations.append(f"Số lượng hoạt động ({len(legs)}) ít hơn tối thiểu yêu cầu ({min_act})")

    # Ràng buộc chi phí
    total_cost = plan.get("total_cost_vnd", 0)
    if total_cost > budget_total:
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
    hard = req.get("hard_constraints", {})
    prefs = req.get("preferences", {})
    num_plans = req.get("number_of_plans", 2)
    members = req.get("group_members", [])

    start_node = req.get("start_node_id", "start_sea_hub")
    end_node = req.get("end_node_id", "start_sea_hub")
    start_time = datetime.fromisoformat(req.get("start_at", "2026-09-18T14:00:00+07:00"))
    deadline = datetime.fromisoformat(req.get("end_by", "2026-09-18T16:00:00+07:00"))
    total_window_minutes = (deadline - start_time).total_seconds() / 60

    indoor_only = hard.get("indoor_only", False)
    max_thrill = hard.get("max_thrill_level", "moderate")
    max_wait = hard.get("max_wait_minutes_per_stop", 20)
    budget_total = hard.get("budget_vnd_total", 150000)
    min_buffer = hard.get("min_end_buffer_minutes", 10)
    allow_unknown = hard.get("allow_unknown_crowd", False)
    min_act = hard.get("min_activity_count", 3)
    excluded = set(hard.get("excluded_service_ids", []))

    # 1. Gọi MCP lấy danh mục và ma trận đường đi
    attractions_list = call_mcp_tool("get_attractions", {"scenario_id": scenario_id})
    attractions_map = {a["service_id"]: a for a in attractions_list}
    all_nodes = [a["location"]["node_id"] for a in attractions_list] + [start_node, end_node]
    route_data = call_mcp_tool("get_route_matrix", {"node_ids": list(set(all_nodes))})
    routes = route_data.get("matrix", {})

    weather_data = call_mcp_tool("get_weather", {"start_at": req.get("start_at"), "end_by": req.get("end_by")})
    weather_windows = weather_data.get("weather_windows", [])

    # Map crowd analysis
    crowd_items = {item["service_id"]: item for item in crowd_analysis.get("items", [])}

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

    if len(eligible_sids) < min_act:
        return {
            "plan_result_id": "res_none",
            "crowd_analysis_id": crowd_analysis.get("analysis_id", ""),
            "scenario_id": scenario_id,
            "data_revision": "v1",
            "status": "no_feasible_plan",
            "plans": [],
            "unfeasible_reasons": [
                f"Chỉ có {len(eligible_sids)} điểm thỏa mãn các tiêu chí (yêu cầu tối thiểu {min_act} điểm).",
                f"Các ràng buộc giới hạn: trong nhà={indoor_only}, chờ tối đa={max_wait}p, cảm giác mạnh={max_thrill}.",
            ],
            "warnings": [],
        }

    # 3. Tìm kiếm các tổ hợp khả thi
    candidate_plans = []
    # Thử độ dài từ min_act đến min(min_act + 2, len(eligible_sids))
    max_len = min(min_act + 1, len(eligible_sids))
    for r in range(min_act, max_len + 1):
        for seq in itertools.permutations(eligible_sids, r):
            curr_time = start_time
            curr_node = start_node
            legs = []
            total_cost = 0
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

                if act_end > deadline:
                    feasible = False
                    break

                # Chi phí
                price_per = attr.get("pricing", {}).get("price_per_person_vnd", 0)
                step_cost = price_per * len(members)
                total_cost += step_cost

                legs.append({
                    "step": step_idx,
                    "service_id": sid,
                    "service_name": attr.get("name", sid),
                    "node_id": dest_node,
                    "arrival_time": arrival.strftime("%H:%M"),
                    "start_time": act_start.strftime("%H:%M"),
                    "end_time": act_end.strftime("%H:%M"),
                    "walk_from_prev_minutes": walk_min,
                    "wait_minutes": wait_min,
                    "activity_duration_minutes": dur_min,
                    "cost_vnd": step_cost,
                    "indoor": attr.get("indoor", False),
                    "note": f"Hàng chờ {wait_min}p, trải nghiệm {dur_min}p",
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
            "data_revision": "v1",
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
            f"thời gian chờ tích lũy chỉ {raw['total_wait']} phút."
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
                print(f"[Agent A1] LLM rationale error: {e}")

        plan_obj = {
            "plan_id": f"plan_opt_{idx}_{style}",
            "style": style,
            "style_label": label,
            "total_duration_minutes": raw["total_duration_minutes"],
            "end_buffer_minutes": raw["end_buffer_minutes"],
            "total_cost_vnd": raw["total_cost_vnd"],
            "start_node_id": raw["start_node_id"],
            "end_node_id": raw["end_node_id"],
            "return_arrival_time": raw["return_arrival_time"],
            "legs": raw["legs"],
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
            "data_revision": "v1",
            "status": "no_feasible_plan",
            "plans": [],
            "unfeasible_reasons": ["Tất cả các phương án sinh ra đều không vượt qua bộ kiểm tra ràng buộc (Validator)."],
            "warnings": [],
        }

    return {
        "plan_result_id": "res_success",
        "crowd_analysis_id": crowd_analysis.get("analysis_id", ""),
        "scenario_id": scenario_id,
        "data_revision": "v1",
        "status": "completed",
        "plans": validated_plans,
        "unfeasible_reasons": [],
        "warnings": [],
    }


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
        inp = req_data.get("input", {})

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
            "data_revision": req_data.get("data_revision", "v1"),
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
    description="Agent chuyên gia lập lịch trình, tối ưu đường đi và kiểm tra ràng buộc vui chơi VinWonders",
    version="1.0.0",
    url="http://127.0.0.1:8001",
    capabilities=AgentCapabilities(),
    default_input_modes=["text"],
    default_output_modes=["text"],
    skills=[
        AgentSkill(
            id="create_plans",
            name="Lập lịch trình",
            description="Tạo và xác thực 1-2 phương án lịch trình theo thời gian thực",
            tags=["planner", "routing", "scheduling"],
        )
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
    return {"status": "ok", "agent": "a1_planner_specialist", "port": "8001", "llm": get_llm_status()}


class DirectPlanRequest(BaseModel):
    normalized_request: dict[str, Any]
    crowd_analysis: dict[str, Any]
    scenario_id: str = "base"


@app.post("/api/plan")
def direct_plan(req: DirectPlanRequest) -> dict[str, Any]:
    return plan_itinerary_logic(req.normalized_request, req.crowd_analysis, req.scenario_id)


if __name__ == "__main__":
    print("Khởi động Agent A1 (Planner Specialist) tại http://127.0.0.1:8001...")
    uvicorn.run(app, host="127.0.0.1", port=8001, log_level="info")
