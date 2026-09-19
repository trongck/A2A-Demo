"""
Agent A0: Điều phối viên (Orchestrator) hệ thống V-AI.
Quản lý phiên, máy trạng thái bằng code, giao tiếp A2A với A2 và A1, lưu trữ SQLite Shared Memory.
Bám sát mục 3, 4, 6 và 7 của V-AI-Implementation-Plan.md.
"""

import copy
import json
import re
import time
import uuid
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from shared.security import get_logger, sanitize_user_input
from shared.security.config import V_AI_INTERNAL_SECRET, INTERNAL_AUTH_ENABLED

from shared.llm import (
    answer_general_chat_with_llm,
    classify_and_extract_intent_with_llm,
    generate_hitl_questions_with_llm,
    generate_unfeasible_explanation_with_llm,
    is_llm_available,
    stream_answer_general_chat_with_llm,
    stream_generate_unfeasible_explanation_with_llm,
    stream_synthesize_chat_response_with_llm,
    synthesize_chat_response_with_llm,
)
from shared.memory.database import (
    add_message,
    get_events,
    get_or_create_session,
    record_event,
    save_agent_result,
    save_plans,
    update_session,
)
from shared.data_adapter import DATA_REVISION, START_NODE_ID, load_ticket_policy, ticket_groups_to_members


logger = get_logger("a0.orchestrator")

A2_URL = "http://127.0.0.1:8002"
A1_URL = "http://127.0.0.1:8001"



def call_a2a_agent(agent_url: str, request_payload: dict[str, Any]) -> dict[str, Any]:
    """Gọi Specialist Agent qua giao thức A2A JSON-RPC / HTTP."""
    # Gọi qua endpoint trực tiếp nếu có hoặc qua JSON-RPC message
    target_action = request_payload.get("action")
    endpoint = f"{agent_url}/api/analyze" if target_action == "analyze_crowd" else f"{agent_url}/api/plan"

    # H5: Thêm internal secret header cho inter-agent auth
    headers: dict[str, str] = {}
    if INTERNAL_AUTH_ENABLED:
        headers["X-Internal-Secret"] = V_AI_INTERNAL_SECRET

    try:
        with httpx.Client(timeout=15.0) as client:
            if target_action == "analyze_crowd":
                resp = client.post(
                    endpoint,
                    headers=headers,
                    json={
                        "scenario_id": request_payload.get("scenario_id", "base"),
                        "service_ids": request_payload.get("input", {}).get("service_ids"),
                    },
                )
            else:
                resp = client.post(
                    endpoint,
                    headers=headers,
                    json={
                        "normalized_request": request_payload.get("input", {}).get("normalized_request", {}),
                        "crowd_analysis": request_payload.get("input", {}).get("crowd_analysis", {}),
                        "scenario_id": request_payload.get("scenario_id", "base"),
                    },
                )

            if resp.status_code == 200:
                result = resp.json()
                if result.get("data_revision") != DATA_REVISION:
                    logger.error("Rejected mismatched agent data revision: %s", result.get("data_revision"))
                    return {"status": "failed", "error": "Phiên bản dữ liệu agent không đồng bộ."}
                return {
                    "status": "completed",
                    "result": result,
                }
    except Exception as e:
        # M6: Log chi tiết nội bộ, không lộ cho client
        logger.warning("A2A call failed to %s: %s", agent_url, e)
        # Fallback local import khi chạy in-process hoặc test
        if target_action == "analyze_crowd":
            from agents.a2.server import analyze_crowd_logic
            res = analyze_crowd_logic(
                scenario_id=request_payload.get("scenario_id", "base"),
                service_ids=request_payload.get("input", {}).get("service_ids"),
            )
            if res.get("data_revision") != DATA_REVISION:
                return {"status": "failed", "error": "Phiên bản dữ liệu agent không đồng bộ."}
            return {"status": "completed", "result": res}
        else:
            from agents.a1.server import plan_itinerary_logic
            res = plan_itinerary_logic(
                normalized_request=request_payload.get("input", {}).get("normalized_request", {}),
                crowd_analysis=request_payload.get("input", {}).get("crowd_analysis", {}),
                scenario_id=request_payload.get("scenario_id", "base"),
            )
            if res.get("data_revision") != DATA_REVISION:
                return {"status": "failed", "error": "Phiên bản dữ liệu agent không đồng bộ."}
            return {"status": res.get("status", "completed"), "result": res}

    # M6: Error message generic, không lộ URL nội bộ
    return {"status": "failed", "error": "Không thể kết nối đến dịch vụ agent nội bộ."}


def extract_or_update_request(
    user_message: str,
    current_session: dict[str, Any],
    preset_data: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], bool, list[str], str, dict[str, Any]]:
    """Trích xuất và chuẩn hóa yêu cầu của người dùng kết hợp LLM và quy tắc logic."""
    profile = copy.deepcopy(current_session.get("profile", {}))
    missing_fields: list[str] = []
    visit_date = datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).date()
    if "ngày mai" in user_message.lower():
        visit_date += timedelta(days=1)

    # Nếu người dùng nạp từ preset (ví dụ preset gia đình)
    if preset_data:
        profile.update(preset_data)

    intent_type = "plan_itinerary"
    routing: dict[str, Any] = {
        "status": "need_clarification",
        "intent": intent_type,
        "completeness": "0/2",
        "filled_criteria": {},
        "clarification": {},
        "fallback_text": "",
        "forward_payload": {},
    }

    # 1. Thử phân loại intent và trích xuất thực thể qua LLM
    if is_llm_available():
        try:
            llm_result = classify_and_extract_intent_with_llm(user_message, profile)
            routing.update(llm_result)
            llm_status = llm_result.get("status")
            if llm_status in {"out_of_scope", "too_ambiguous"}:
                intent_type = llm_status
            else:
                intent_type = llm_result.get("intent") or "plan_itinerary"
            entities = llm_result.get("entities", {})

            if entities.get("indoor_only") is not None:
                profile.setdefault("hard_constraints", {})["indoor_only"] = entities["indoor_only"]
            if entities.get("min_activity_count") is not None:
                profile.setdefault("hard_constraints", {})["min_activity_count"] = entities["min_activity_count"]
                profile.pop("needs_activity_count", None)
            elif entities.get("wants_multiple_places") is True:
                profile["needs_activity_count"] = True

            ticket_groups = entities.get("ticket_groups")
            if isinstance(ticket_groups, dict):
                valid_group_ids = {group["id"] for group in load_ticket_policy()["visitor_groups"]}
                normalized_groups = {
                    group_id: int(count)
                    for group_id, count in ticket_groups.items()
                    if group_id in valid_group_ids and isinstance(count, (int, float)) and int(count) > 0
                }
                if normalized_groups:
                    profile["ticket_groups"] = normalized_groups
                    profile["group_members"] = ticket_groups_to_members(normalized_groups)
                    profile.setdefault("pending_group_details", {})["group_size"] = sum(normalized_groups.values())
            if entities.get("max_wait_minutes") is not None:
                profile.setdefault("hard_constraints", {})["max_wait_minutes_per_stop"] = entities["max_wait_minutes"]

            if entities.get("height_cm") is not None:
                profile.setdefault("pending_group_details", {})["height_cm"] = int(entities["height_cm"])

            if entities.get("age_years") is not None:
                profile.setdefault("pending_group_details", {})["age_years"] = int(entities["age_years"])

            if entities.get("group_size") is not None:
                profile.setdefault("pending_group_details", {})["group_size"] = int(entities["group_size"])

            extracted_members = entities.get("group_members")
            if isinstance(extracted_members, list) and extracted_members:
                complete_members = []
                for index, member in enumerate(extracted_members, 1):
                    if (
                        not isinstance(member, dict)
                        or member.get("age_years") is None
                        or member.get("height_cm") is None
                    ):
                        complete_members = []
                        break
                    complete_members.append({
                        "member_id": member.get("member_id") or f"member_{index}",
                        "age_years": int(member["age_years"]),
                        "height_cm": int(member["height_cm"]),
                    })
                if complete_members:
                    profile["group_members"] = complete_members

            if entities.get("time_hours") is not None:
                profile["pending_duration_hours"] = float(entities["time_hours"])

            if entities.get("start_time"):
                st = str(entities["start_time"]).strip()
                if len(st) == 5 and ":" in st:
                    profile["start_at"] = f"{visit_date.isoformat()}T{st}:00+07:00"

            if entities.get("end_time"):
                et = str(entities["end_time"]).strip()
                if len(et) == 5 and ":" in et:
                    profile["end_by"] = f"{visit_date.isoformat()}T{et}:00+07:00"

        except Exception as e:
            logger.warning("LLM intent extraction error: %s", e)

    # 2. Xử lý logic quy tắc bổ trợ
    msg_lower = user_message.lower()

    planning_keywords = [
        "gợi ý", "lập lịch", "lên lịch", "lịch trình", "kế hoạch", "chơi gì",
        "trò chơi", "điểm chơi", "tham quan", "tư vấn", "lộ trình",
    ]
    is_hitl_summary = "thông tin bổ sung đã xác nhận:" in msg_lower
    if is_hitl_summary:
        intent_type = "plan_itinerary"
    elif intent_type not in {"out_of_scope", "too_ambiguous"} and any(k in msg_lower for k in planning_keywords):
        intent_type = "plan_itinerary"

    if not is_llm_available():
        normalized = re.sub(r"[^a-z0-9à-ỹ]+", " ", msg_lower).strip()
        if normalized in {"hi", "hello", "xin chào", "chào", "chào bạn"}:
            intent_type = "general_chat"
        elif any(k in msg_lower for k in ("giá vàng", "chứng khoán", "tiền ảo", "bóng đá")):
            intent_type = "out_of_scope"
        elif normalized in {"giúp tôi", "tư vấn", "hỗ trợ tôi", "tôi cần giúp"}:
            intent_type = "too_ambiguous"

    if "chỉ trong nhà" in msg_lower or "chỉ đi trong nhà" in msg_lower or "indoor" in msg_lower:
        hard = profile.setdefault("hard_constraints", {})
        hard["indoor_only"] = True

    if "ngoài trời" in msg_lower:
        hard = profile.setdefault("hard_constraints", {})
        hard["indoor_only"] = False

    match_min_act = re.search(r"tối thiểu\s+(\d+)\s+điểm", msg_lower)
    if match_min_act:
        hard = profile.setdefault("hard_constraints", {})
        hard["min_activity_count"] = int(match_min_act.group(1))

    match_duration = re.search(r"(\d+(?:[.,]\d+)?)\s*(?:tiếng|giờ)", msg_lower)
    if match_duration:
        profile["pending_duration_hours"] = float(match_duration.group(1).replace(",", "."))

    # Nếu chưa có thông tin thành viên
    if not profile.get("group_members"):
        match_height = re.search(r"cao\s+(\d+)\s*cm", msg_lower)
        if match_height:
            profile.setdefault("pending_group_details", {})["height_cm"] = int(match_height.group(1))
        match_age = re.search(r"(\d{1,2})\s*tuổi", msg_lower)
        if match_age:
            profile.setdefault("pending_group_details", {})["age_years"] = int(match_age.group(1))

        # Chỉ cần hồ sơ an toàn đại diện, không bắt khách khai từng thành viên.
        pending = profile.get("pending_group_details", {})
        group_size = pending.get("group_size")
        min_age = pending.get("age_years")
        min_height = pending.get("height_cm")
        if group_size and min_age is not None and min_height is not None:
            profile["group_members"] = [
                {
                    "member_id": f"member_{index}",
                    "age_years": int(min_age),
                    "height_cm": int(min_height),
                }
                for index in range(1, int(group_size) + 1)
            ]
            profile["group_profile_ranges"] = {
                "group_size": int(group_size),
                "minimum_age_years": int(min_age),
                "minimum_height_cm": int(min_height),
            }
        if intent_type not in {"general_chat", "out_of_scope", "too_ambiguous"}:
            if not profile.get("group_members"):
                missing_fields.append("thông_tin_thành_viên")

    if profile.get("needs_activity_count"):
        missing_fields.append("số_điểm_mong_muốn")

    if not profile.get("start_at") or not profile.get("end_by"):
        explicit_window = re.search(
            r"(?:từ\s*)?(\d{1,2})(?::(\d{2}))?\s*h?\s*(?:đến|tới|-|–)\s*(\d{1,2})(?::(\d{2}))?\s*h?",
            msg_lower,
        )
        if explicit_window:
            start_hour, start_minute, end_hour, end_minute = explicit_window.groups()
            profile["start_at"] = f"{visit_date.isoformat()}T{int(start_hour):02d}:{int(start_minute or 0):02d}:00+07:00"
            profile["end_by"] = f"{visit_date.isoformat()}T{int(end_hour):02d}:{int(end_minute or 0):02d}:00+07:00"
        elif "cả ngày" in msg_lower:
            profile["start_at"] = f"{visit_date.isoformat()}T09:00:00+07:00"
            profile["end_by"] = f"{visit_date.isoformat()}T20:00:00+07:00"
        elif intent_type not in {"general_chat", "out_of_scope", "too_ambiguous"}:
            missing_fields.append("khung_giờ_tham_quan")

    # Mặc định các thông số tiêu chuẩn nếu chưa có
    if profile.get("start_node_id") in {None, "start_sea_hub"}:
        profile["start_node_id"] = START_NODE_ID
    if profile.get("end_node_id") in {None, "start_sea_hub"}:
        profile["end_node_id"] = START_NODE_ID
    profile.setdefault("number_of_plans", 2)
    hard_defaults = {
        "indoor_only": False,
        "max_thrill_level": "moderate",
        "max_wait_minutes_per_stop": 20,
        "budget_vnd_total": None,
        "min_end_buffer_minutes": 10,
        "allow_unknown_crowd": True,
        "excluded_service_ids": [],
        "min_activity_count": 3,
    }
    hard_constraints = profile.setdefault("hard_constraints", {})
    for key, value in hard_defaults.items():
        hard_constraints.setdefault(key, value)

    preference_defaults = {
        "prioritize_low_crowd": True,
        "meal_required": False,
        "plan_styles": ["gentle", "more_rides"],
    }
    preferences = profile.setdefault("preferences", {})
    for key, value in preference_defaults.items():
        preferences.setdefault(key, value)

    filled_criteria: dict[str, Any] = {"điểm_đến": "VinWonders Nha Trang"}
    if profile.get("group_members"):
        filled_criteria["thông_tin_thành_viên"] = profile["group_members"]
    if profile.get("start_at") and profile.get("end_by"):
        filled_criteria["khung_giờ_tham_quan"] = {
            "start_at": profile["start_at"],
            "end_by": profile["end_by"],
        }

    clarification = None
    if missing_fields and is_llm_available():
        try:
            clarification = generate_hitl_questions_with_llm(user_message, profile, missing_fields)
        except Exception as e:
            logger.warning("LLM HITL question generation error: %s", e)

    if intent_type == "out_of_scope":
        routing.update({
            "status": "out_of_scope",
            "intent": None,
            "completeness": "",
            "filled_criteria": {},
            "clarification": {},
            "fallback_text": (
                "Mình chuyên hỗ trợ trải nghiệm tại VinWonders Nha Trang. "
                "Bạn muốn hỏi về điểm vui chơi hay lên lịch trình tham quan không?"
            ),
            "forward_payload": {},
        })
    elif intent_type == "too_ambiguous":
        routing.update({
            "status": "too_ambiguous",
            "intent": None,
            "completeness": "",
            "filled_criteria": {},
            "clarification": {},
            "fallback_text": (
                "Bạn muốn mình hỗ trợ thông tin điểm vui chơi hay thiết kế lịch trình tại VinWonders Nha Trang?"
            ),
            "forward_payload": {},
        })
    elif intent_type == "general_chat":
        routing.update({
            "status": "ready",
            "intent": "general_chat",
            "completeness": "0/0",
            "filled_criteria": {},
            "clarification": {},
            "fallback_text": "",
            "forward_payload": {},
        })
    else:
        criteria_total = 2 + int("số_điểm_mong_muốn" in missing_fields)
        completed_count = criteria_total - len(missing_fields)
        routing.update({
            "status": "ready" if not missing_fields else "need_clarification",
            "intent": intent_type,
            "completeness": f"{completed_count}/{criteria_total}",
            "filled_criteria": filled_criteria,
            "clarification": clarification or {},
            "fallback_text": "",
            "forward_payload": profile if not missing_fields else {},
        })

    is_complete = len(missing_fields) == 0 and intent_type in {"plan_itinerary", "adjust_plan"}
    return profile, is_complete, missing_fields, intent_type, routing



# --- State Machine Điều phối chính ---

def run_orchestration(
    session_id: str,
    user_message: str,
    scenario_override: str | None = None,
    preset_data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Hàm điều phối tuần tự của Agent A0:
    User Message -> Intent -> (Hỏi nếu thiếu) -> A2 (Crowd) -> Memory -> A1 (Planner) -> Validator -> User Reply.
    """
    turn_id = f"turn_{uuid.uuid4().hex[:6]}"
    start_turn_time = time.time()

    # 1. Khởi tạo / đọc Session từ SQLite
    session = get_or_create_session(session_id)
    scenario_id = scenario_override or session.get("scenario_id", "base")

    # Lưu tin nhắn người dùng
    add_message(session_id, turn_id, "user", user_message)
    record_event(
        session_id=session_id,
        turn_id=turn_id,
        event_type="user_message",
        sender="User",
        receiver="A0",
        summary=f"Người dùng gửi yêu cầu: '{user_message[:80]}...'",
        payload={"message": user_message, "scenario_id": scenario_id},
        status="info",
    )
    # H3: Sanitize user input trước khi xử lý
    user_message = sanitize_user_input(user_message)

    # 2. Phân loại yêu cầu & Chuẩn hóa dữ liệu
    t_start = time.time()
    updated_profile, is_complete, missing_fields, intent_type, routing = extract_or_update_request(
        user_message=user_message,
        current_session=session,
        preset_data=preset_data,
    )
    extract_duration = int((time.time() - t_start) * 1000)

    # 3a. Ngoài phạm vi / quá mơ hồ: A0 dừng điều phối, không gọi A2/A1.
    if intent_type in {"out_of_scope", "too_ambiguous"}:
        fallback_text = routing["fallback_text"]
        add_message(session_id, turn_id, "assistant", fallback_text)
        record_event(
            session_id=session_id,
            turn_id=turn_id,
            event_type="a0_route",
            sender="A0",
            receiver="User",
            summary=f"A0 dừng điều phối với trạng thái {intent_type}.",
            payload=routing,
            duration_ms=extract_duration,
            status="info",
        )
        return {
            "session_id": session_id,
            "turn_id": turn_id,
            "status": intent_type,
            "reply": fallback_text,
            "plans": [],
            "routing": routing,
        }

    # 3b. Nếu là General Chat (chào hỏi, hỏi thông tin công viên)
    if intent_type == "general_chat":
        t_chat = time.time()
        chat_reply = answer_general_chat_with_llm(user_message)
        if not chat_reply:
            chat_reply = (
                "Xin chào bạn! Mình là V-AI, người bạn đồng hành tại VinWonders Nha Trang. "
                "Tôi có thể hỗ trợ bạn thông tin về các phân khu vui chơi và lên kế hoạch trải nghiệm tối ưu cho cả đoàn. "
                "Bạn muốn bắt đầu lên lịch trình tham quan lúc mấy giờ?"
            )
        chat_dur = int((time.time() - t_chat) * 1000)
        add_message(session_id, turn_id, "assistant", chat_reply)
        record_event(
            session_id=session_id,
            turn_id=turn_id,
            event_type="a0_chat",
            sender="A0",
            receiver="User",
            summary="A0 trả lời tư vấn / trò chuyện tự nhiên cùng khách bằng LLM.",
            payload={"message": user_message, "response": chat_reply},
            duration_ms=chat_dur,
            status="info",
        )
        return {
            "session_id": session_id,
            "turn_id": turn_id,
            "status": "completed",
            "reply": chat_reply,
            "plans": [],
            "routing": routing,
        }

    # 3c. Xử lý trường hợp thiếu thông tin bắt buộc khi lập lịch
    if not is_complete:
        t_clarify = time.time()
        clarification = routing.get("clarification", {})
        clarification_msg = clarification.get("message") or (
            "Mình cần thêm một chút thông tin để lên lịch an toàn nhé."
        )
        memory_version = update_session(session_id, profile=updated_profile, scenario_id=scenario_id)
        clarify_duration = int((time.time() - t_clarify) * 1000)
        add_message(session_id, turn_id, "assistant", clarification_msg)
        record_event(
            session_id=session_id,
            turn_id=turn_id,
            event_type="a0_intent",
            sender="A0",
            receiver="User",
            summary=f"Yêu cầu thiếu dữ liệu: {missing_fields}. A0 đã lưu hồ sơ từng phần ở v{memory_version}.",
            payload={
                "missing_fields": missing_fields,
                "response": clarification_msg,
                "clarification": clarification,
                "memory_version": memory_version,
            },
            duration_ms=clarify_duration,
            status="warning",
        )
        return {
            "session_id": session_id,
            "turn_id": turn_id,
            "status": "needs_input",
            "reply": clarification_msg,
            "plans": [],
            "missing_fields": missing_fields,
            "clarification": clarification,
            "routing": routing,
            "memory_version": memory_version,
        }


    # Cập nhật context vào SQLite (tự động tăng version)
    new_version = update_session(session_id, profile=updated_profile, scenario_id=scenario_id)
    record_event(
        session_id=session_id,
        turn_id=turn_id,
        event_type="a0_intent",
        sender="A0",
        receiver="SharedMemory",
        summary=f"Yêu cầu đã được chuẩn hóa. Lưu context phiên bản v{new_version}.",
        payload=updated_profile,
        duration_ms=extract_duration,
        status="success",
    )

    # 4. A0 gọi Agent A2 (Crowd Specialist)
    t_a2 = time.time()
    record_event(
        session_id=session_id,
        turn_id=turn_id,
        event_type="a0_call_a2",
        sender="A0",
        receiver="A2",
        summary="A0 chuyển giao nhiệm vụ phân tích mật độ cho Agent A2 qua A2A protocol.",
        payload={"scenario_id": scenario_id, "memory_version": new_version},
        status="info",
    )

    a2_req = {
        "schema_version": "1.0",
        "session_id": session_id,
        "turn_id": turn_id,
        "request_id": f"req_a2_{turn_id}",
        "action": "analyze_crowd",
        "memory_ref": {"session_id": session_id, "version": new_version},
        "scenario_id": scenario_id,
        "data_revision": DATA_REVISION,
        "input": {"service_ids": None},
    }

    a2_resp = call_a2a_agent(A2_URL, a2_req)
    a2_duration = int((time.time() - t_a2) * 1000)

    if a2_resp.get("status") != "completed":
        err_msg = f"Agent A2 gặp lỗi khi phân tích."
        record_event(
            session_id=session_id,
            turn_id=turn_id,
            event_type="error",
            sender="A2",
            receiver="A0",
            summary=err_msg,
            payload=a2_resp,
            duration_ms=a2_duration,
            status="error",
        )
        return {
            "session_id": session_id,
            "turn_id": turn_id,
            "status": "failed",
            "reply": "Xin lỗi quý khách, hệ thống phân tích mật độ hiện đang bận. Vui lòng thử lại trong giây lát.",
            "plans": [],
            "routing": routing,
        }

    crowd_analysis = a2_resp["result"]
    # Lưu kết quả A2 vào SQLite
    save_agent_result(session_id, turn_id, "a2_crowd_specialist", crowd_analysis)
    a2_version = update_session(session_id, profile=None)

    record_event(
        session_id=session_id,
        turn_id=turn_id,
        event_type="a2_result",
        sender="A2",
        receiver="A0",
        summary=f"A2 hoàn thành phân tích {len(crowd_analysis.get('items', []))} điểm vui chơi. Lưu memory v{a2_version}.",
        payload={
            "analysis_id": crowd_analysis.get("analysis_id"),
            "items_count": len(crowd_analysis.get("items", [])),
            "warnings": crowd_analysis.get("warnings", []),
        },
        duration_ms=a2_duration,
        status="success",
    )

    # 5. A0 gọi Agent A1 (Planner Specialist)
    t_a1 = time.time()
    record_event(
        session_id=session_id,
        turn_id=turn_id,
        event_type="a0_call_a1",
        sender="A0",
        receiver="A1",
        summary="A0 chuyển giao phân tích A2 cho Agent A1 lập lịch trình qua A2A protocol.",
        payload={"crowd_analysis_id": crowd_analysis.get("analysis_id"), "memory_version": a2_version},
        status="info",
    )

    a1_req = {
        "schema_version": "1.0",
        "session_id": session_id,
        "turn_id": turn_id,
        "request_id": f"req_a1_{turn_id}",
        "action": "create_plans",
        "memory_ref": {"session_id": session_id, "version": a2_version},
        "scenario_id": scenario_id,
        "data_revision": DATA_REVISION,
        "input": {
            "normalized_request": updated_profile,
            "crowd_analysis": crowd_analysis,
        },
    }

    a1_resp = call_a2a_agent(A1_URL, a1_req)
    a1_duration = int((time.time() - t_a1) * 1000)

    plan_result = a1_resp.get("result", {})
    plans = plan_result.get("plans", [])
    plan_status = plan_result.get("status", "failed")
    if plan_result:
        save_agent_result(session_id, turn_id, "a1_planner_specialist", plan_result)

    if a1_resp.get("status") == "failed" or plan_status == "failed":
        reply = "Xin lỗi quý khách, dịch vụ lập lịch chưa đồng bộ dữ liệu V2. Vui lòng thử lại sau khi các agent được khởi động lại."
        add_message(session_id, turn_id, "assistant", reply)
        record_event(
            session_id=session_id,
            turn_id=turn_id,
            event_type="error",
            sender="A1",
            receiver="A0",
            summary="A1 từ chối lập lịch do lỗi dịch vụ hoặc data revision.",
            payload=a1_resp,
            duration_ms=a1_duration,
            status="error",
        )
        return {
            "session_id": session_id,
            "turn_id": turn_id,
            "status": "failed",
            "reply": reply,
            "plans": [],
            "routing": routing,
        }

    if plan_status == "no_feasible_plan":
        unfeasible_reasons = plan_result.get("unfeasible_reasons", [])
        explanation = None
        if is_llm_available():
            try:
                explanation = generate_unfeasible_explanation_with_llm(
                    user_message=user_message,
                    unfeasible_reasons=unfeasible_reasons,
                    current_constraints=updated_profile.get("hard_constraints", {}),
                )
            except Exception as e:
                logger.warning("LLM unfeasible explanation error: %s", e)

        if not explanation:
            explanation = (
                "Dựa trên dữ liệu thực tế tại công viên, hiện không có phương án nào đáp ứng trọn vẹn mọi yêu cầu của quý khách.\n"
                + "\n".join(f"- {r}" for r in unfeasible_reasons)
                + "\nQuý khách có thể nới lỏng thời gian chờ tối đa, tăng khung giờ chơi hoặc cho phép chơi ngoài trời để tôi lập lại lịch nhé!"
            )
        add_message(session_id, turn_id, "assistant", explanation)

        record_event(
            session_id=session_id,
            turn_id=turn_id,
            event_type="a1_result",
            sender="A1",
            receiver="A0",
            summary=f"A1 báo cáo không có phương án khả thi ({len(unfeasible_reasons)} ràng buộc nghẽn).",
            payload=plan_result,
            duration_ms=a1_duration,
            status="warning",
        )
        return {
            "session_id": session_id,
            "turn_id": turn_id,
            "status": "no_feasible_plan",
            "reply": explanation,
            "plans": [],
            "unfeasible_reasons": unfeasible_reasons,
            "routing": routing,
        }

    # Lưu phương án vào SQLite
    save_plans(session_id, turn_id, plans)

    record_event(
        session_id=session_id,
        turn_id=turn_id,
        event_type="a1_result",
        sender="A1",
        receiver="A0",
        summary=f"A1 đã lập và kiểm tra thành công {len(plans)} phương án lịch trình qua Validator xác định.",
        payload={
            "plan_result_id": plan_result.get("plan_result_id"),
            "plans_summary": [
                {
                    "style": p["style"],
                    "duration": p["total_duration_minutes"],
                    "buffer": p["end_buffer_minutes"],
                    "services": p["service_ids"],
                }
                for p in plans
            ],
        },
        duration_ms=a1_duration,
        status="success",
    )

    # 6. A0 tổng hợp câu trả lời tự nhiên cho người dùng (ưu tiên LLM nếu có)
    llm_reply = None
    if is_llm_available():
        try:
            llm_reply = synthesize_chat_response_with_llm(user_message, plans, crowd_analysis)
        except Exception as e:
            logger.warning("LLM synthesis error: %s", e)

    if llm_reply:
        full_reply = llm_reply
    else:

        reply_lines = [
            f"Dạ, V-AI đã thiết lập {len(plans)} phương án tối ưu cho đoàn của bạn:\n"
        ]
        for idx, p in enumerate(plans, 1):
            reply_lines.append(
                f"**{p['style_label']}**:\n"
                f"• Lộ trình: {' ➔ '.join(leg['service_name'] for leg in p['legs'])}\n"
                f"• Tổng thời gian dự kiến: **{p['total_duration_minutes']} phút** (kết thúc và về lại lúc {p['return_arrival_time']})\n"
                f"• Thời gian dự phòng trước 16:00: **{p['end_buffer_minutes']} phút**\n"
                f"• Tổng chi phí đoàn: **{p['total_cost_vnd']:,} VNĐ**\n"
                f"• Lý do: {p['rationale']}\n"
            )
        reply_lines.append("Quý khách có thể xem chi tiết từng chặng ở thẻ bên dưới hoặc tiếp tục chat để điều chỉnh (ví dụ: 'chỉ đi trong nhà', 'đổi thời gian')!")
        full_reply = "\n".join(reply_lines)

    add_message(session_id, turn_id, "assistant", full_reply)


    total_turn_duration = int((time.time() - start_turn_time) * 1000)
    record_event(
        session_id=session_id,
        turn_id=turn_id,
        event_type="a0_reply",
        sender="A0",
        receiver="User",
        summary=f"A0 hoàn thành lượt hội thoại, trình bày {len(plans)} phương án cho khách.",
        payload={"plans_count": len(plans), "total_turn_ms": total_turn_duration},
        duration_ms=total_turn_duration,
        status="success",
    )

    return {
        "session_id": session_id,
        "turn_id": turn_id,
        "status": "completed",
        "reply": full_reply,
        "plans": plans,
        "crowd_analysis": crowd_analysis,
        "routing": routing,
    }


def run_orchestration_stream(
    session_id: str,
    user_message: str,
    scenario_override: str | None = None,
    preset_data: dict[str, Any] | None = None,
) -> Any:
    """Hàm điều phối tuần tự của Agent A0 dưới dạng SSE Stream."""
    turn_id = f"turn_{uuid.uuid4().hex[:6]}"
    start_turn_time = time.time()

    session = get_or_create_session(session_id)
    scenario_id = scenario_override or session.get("scenario_id", "base")

    add_message(session_id, turn_id, "user", user_message)
    record_event(
        session_id=session_id,
        turn_id=turn_id,
        event_type="user_message",
        sender="User",
        receiver="A0",
        summary=f"Người dùng gửi yêu cầu: '{user_message[:80]}...'",
        payload={"message": user_message, "scenario_id": scenario_id},
        status="info",
    )

    # H3: Sanitize user input trước khi xử lý
    user_message = sanitize_user_input(user_message)

    yield f"event: thinking\ndata: {json.dumps({'stage': 'intent', 'message': 'Agent A0 đang phân tích nội dung và ràng buộc...'}, ensure_ascii=False)}\n\n"

    t_start = time.time()
    updated_profile, is_complete, missing_fields, intent_type, routing = extract_or_update_request(
        user_message=user_message,
        current_session=session,
        preset_data=preset_data,
    )
    extract_duration = int((time.time() - t_start) * 1000)

    if intent_type in {"out_of_scope", "too_ambiguous"}:
        fallback_text = routing["fallback_text"]
        yield f"event: token\ndata: {json.dumps({'token': fallback_text}, ensure_ascii=False)}\n\n"
        add_message(session_id, turn_id, "assistant", fallback_text)
        record_event(
            session_id=session_id,
            turn_id=turn_id,
            event_type="a0_route",
            sender="A0",
            receiver="User",
            summary=f"A0 dừng điều phối với trạng thái {intent_type}.",
            payload=routing,
            duration_ms=extract_duration,
            status="info",
        )
        done_payload = {
            "session_id": session_id,
            "turn_id": turn_id,
            "status": intent_type,
            "reply": fallback_text,
            "plans": [],
            "routing": routing,
            "events": get_events(session_id),
        }
        yield f"event: done\ndata: {json.dumps(done_payload, ensure_ascii=False)}\n\n"
        return

    # 1. Nhánh General Chat
    if intent_type == "general_chat":
        yield f"event: thinking\ndata: {json.dumps({'stage': 'generating', 'message': 'Agent A0 đang phản hồi câu hỏi của bạn...'}, ensure_ascii=False)}\n\n"
        accumulated_reply = ""
        try:
            for token in stream_answer_general_chat_with_llm(user_message):
                accumulated_reply += token
                yield f"event: token\ndata: {json.dumps({'token': token}, ensure_ascii=False)}\n\n"
        except Exception as e:
            logger.warning("Stream general chat error: %s", e)

        if not accumulated_reply:
            fallback = (
                "Xin chào bạn! Tôi là Hướng dẫn viên ảo kiêm Điều phối viên hệ thống V-AI tại VinWonders Nha Trang. "
                "Tôi có thể hỗ trợ bạn thông tin về các phân khu vui chơi và lên kế hoạch trải nghiệm tối ưu cho cả đoàn. "
                "Bạn muốn bắt đầu lên lịch trình tham quan lúc mấy giờ?"
            )
            accumulated_reply = fallback
            yield f"event: token\ndata: {json.dumps({'token': fallback}, ensure_ascii=False)}\n\n"

        add_message(session_id, turn_id, "assistant", accumulated_reply)
        chat_dur = int((time.time() - t_start) * 1000)
        record_event(
            session_id=session_id,
            turn_id=turn_id,
            event_type="a0_chat",
            sender="A0",
            receiver="User",
            summary="A0 trả lời tư vấn / trò chuyện tự nhiên cùng khách bằng LLM Stream.",
            payload={"message": user_message, "response": accumulated_reply},
            duration_ms=chat_dur,
            status="info",
        )
        yield f"event: done\ndata: {json.dumps({'session_id': session_id, 'turn_id': turn_id, 'status': 'completed', 'reply': accumulated_reply, 'plans': [], 'events': get_events(session_id)}, ensure_ascii=False)}\n\n"
        return

    # 2. Nhánh thiếu thông tin khi lập lịch
    if not is_complete:
        yield f"event: thinking\ndata: {json.dumps({'stage': 'clarifying', 'message': 'Agent A0 đang chuẩn bị câu hỏi làm rõ các tiêu chí an toàn...'}, ensure_ascii=False)}\n\n"
        clarification = routing.get("clarification", {})
        accumulated_reply = clarification.get("message") or (
            "Mình cần thêm một chút thông tin để lên lịch an toàn nhé."
        )
        memory_version = update_session(session_id, profile=updated_profile, scenario_id=scenario_id)
        yield f"event: token\ndata: {json.dumps({'token': accumulated_reply}, ensure_ascii=False)}\n\n"

        add_message(session_id, turn_id, "assistant", accumulated_reply)
        clarify_duration = int((time.time() - t_start) * 1000)
        record_event(
            session_id=session_id,
            turn_id=turn_id,
            event_type="a0_intent",
            sender="A0",
            receiver="User",
            summary=f"Yêu cầu thiếu dữ liệu: {missing_fields}. A0 đã lưu hồ sơ từng phần ở v{memory_version}.",
            payload={
                "missing_fields": missing_fields,
                "response": accumulated_reply,
                "clarification": clarification,
                "memory_version": memory_version,
            },
            duration_ms=clarify_duration,
            status="warning",
        )
        done_payload = {
            "session_id": session_id,
            "turn_id": turn_id,
            "status": "needs_input",
            "reply": accumulated_reply,
            "missing_fields": missing_fields,
            "clarification": clarification,
            "routing": routing,
            "memory_version": memory_version,
            "plans": [],
            "events": get_events(session_id),
        }
        yield f"event: done\ndata: {json.dumps(done_payload, ensure_ascii=False)}\n\n"
        return

    # 3. Đầy đủ thông tin: Tiến hành điều phối A0 -> A2 -> A1
    new_version = update_session(session_id, profile=updated_profile, scenario_id=scenario_id)
    record_event(
        session_id=session_id,
        turn_id=turn_id,
        event_type="a0_intent",
        sender="A0",
        receiver="SharedMemory",
        summary=f"Yêu cầu đã được chuẩn hóa. Lưu context phiên bản v{new_version}.",
        payload=updated_profile,
        duration_ms=extract_duration,
        status="success",
    )

    # 4. Gọi Agent A2
    yield f"event: thinking\ndata: {json.dumps({'stage': 'a2_crowd', 'message': 'Chuyển giao cho Agent A2 phân tích mật độ & hàng chờ thời gian thực...'}, ensure_ascii=False)}\n\n"
    t_a2 = time.time()
    record_event(
        session_id=session_id,
        turn_id=turn_id,
        event_type="a0_call_a2",
        sender="A0",
        receiver="A2",
        summary="A0 chuyển giao nhiệm vụ phân tích mật độ cho Agent A2 qua A2A protocol.",
        payload={"scenario_id": scenario_id, "memory_version": new_version},
        status="info",
    )

    a2_req = {
        "schema_version": "1.0",
        "session_id": session_id,
        "turn_id": turn_id,
        "request_id": f"req_a2_{turn_id}",
        "action": "analyze_crowd",
        "memory_ref": {"session_id": session_id, "version": new_version},
        "scenario_id": scenario_id,
        "data_revision": DATA_REVISION,
        "input": {"service_ids": None},
    }

    a2_resp = call_a2a_agent(A2_URL, a2_req)
    a2_duration = int((time.time() - t_a2) * 1000)

    if a2_resp.get("status") != "completed":
        err_msg = "Xin lỗi quý khách, hệ thống phân tích mật độ hiện đang bận. Vui lòng thử lại trong giây lát."
        record_event(
            session_id=session_id,
            turn_id=turn_id,
            event_type="error",
            sender="A2",
            receiver="A0",
            summary=f"Agent A2 gặp lỗi: {a2_resp.get('error')}",
            payload=a2_resp,
            duration_ms=a2_duration,
            status="error",
        )
        add_message(session_id, turn_id, "assistant", err_msg)
        yield f"event: token\ndata: {json.dumps({'token': err_msg}, ensure_ascii=False)}\n\n"
        yield f"event: done\ndata: {json.dumps({'session_id': session_id, 'turn_id': turn_id, 'status': 'failed', 'reply': err_msg, 'plans': [], 'events': get_events(session_id)}, ensure_ascii=False)}\n\n"
        return

    crowd_analysis = a2_resp["result"]
    save_agent_result(session_id, turn_id, "a2_crowd_specialist", crowd_analysis)
    a2_version = update_session(session_id, profile=None)
    record_event(
        session_id=session_id,
        turn_id=turn_id,
        event_type="a2_result",
        sender="A2",
        receiver="A0",
        summary=f"A2 hoàn thành phân tích {len(crowd_analysis.get('items', []))} điểm vui chơi. Lưu memory v{a2_version}.",
        payload={
            "analysis_id": crowd_analysis.get("analysis_id"),
            "items_count": len(crowd_analysis.get("items", [])),
            "warnings": crowd_analysis.get("warnings", []),
        },
        duration_ms=a2_duration,
        status="success",
    )

    # 5. Gọi Agent A1
    yield f"event: thinking\ndata: {json.dumps({'stage': 'a1_plan', 'message': 'Chuyển giao cho Agent A1 lập lịch trình & kiểm tra ràng buộc qua Validator...'}, ensure_ascii=False)}\n\n"
    t_a1 = time.time()
    record_event(
        session_id=session_id,
        turn_id=turn_id,
        event_type="a0_call_a1",
        sender="A0",
        receiver="A1",
        summary="A0 chuyển giao phân tích A2 cho Agent A1 lập lịch trình qua A2A protocol.",
        payload={"crowd_analysis_id": crowd_analysis.get("analysis_id"), "memory_version": a2_version},
        status="info",
    )

    a1_req = {
        "schema_version": "1.0",
        "session_id": session_id,
        "turn_id": turn_id,
        "request_id": f"req_a1_{turn_id}",
        "action": "create_plans",
        "memory_ref": {"session_id": session_id, "version": a2_version},
        "scenario_id": scenario_id,
        "data_revision": DATA_REVISION,
        "input": {
            "normalized_request": updated_profile,
            "crowd_analysis": crowd_analysis,
        },
    }

    a1_resp = call_a2a_agent(A1_URL, a1_req)
    a1_duration = int((time.time() - t_a1) * 1000)

    plan_result = a1_resp.get("result", {})
    plans = plan_result.get("plans", [])
    plan_status = plan_result.get("status", "failed")
    if plan_result:
        save_agent_result(session_id, turn_id, "a1_planner_specialist", plan_result)

    if a1_resp.get("status") == "failed" or plan_status == "failed":
        reply = "Xin lỗi quý khách, dịch vụ lập lịch chưa đồng bộ dữ liệu V2. Vui lòng thử lại sau khi các agent được khởi động lại."
        add_message(session_id, turn_id, "assistant", reply)
        record_event(
            session_id=session_id,
            turn_id=turn_id,
            event_type="error",
            sender="A1",
            receiver="A0",
            summary="A1 từ chối lập lịch do lỗi dịch vụ hoặc data revision.",
            payload=a1_resp,
            duration_ms=a1_duration,
            status="error",
        )
        yield f"event: token\ndata: {json.dumps({'token': reply}, ensure_ascii=False)}\n\n"
        yield f"event: done\ndata: {json.dumps({'session_id': session_id, 'turn_id': turn_id, 'status': 'failed', 'reply': reply, 'plans': [], 'events': get_events(session_id)}, ensure_ascii=False)}\n\n"
        return

    if plan_status == "no_feasible_plan":
        unfeasible_reasons = plan_result.get("unfeasible_reasons", [])
        yield f"event: thinking\ndata: {json.dumps({'stage': 'generating', 'message': 'Agent A0 đang giải thích chi tiết các ràng buộc chưa thỏa mãn...'}, ensure_ascii=False)}\n\n"
        accumulated_reply = ""
        try:
            for token in stream_generate_unfeasible_explanation_with_llm(
                user_message=user_message,
                unfeasible_reasons=unfeasible_reasons,
                current_constraints=updated_profile.get("hard_constraints", {}),
            ):
                accumulated_reply += token
                yield f"event: token\ndata: {json.dumps({'token': token}, ensure_ascii=False)}\n\n"
        except Exception as e:
            logger.warning("Stream unfeasible explanation error: %s", e)

        if not accumulated_reply:
            accumulated_reply = (
                "Dựa trên dữ liệu thực tế tại công viên, hiện không có phương án nào đáp ứng trọn vẹn mọi yêu cầu của quý khách.\n"
                + "\n".join(f"- {r}" for r in unfeasible_reasons)
                + "\nQuý khách có thể nới lỏng thời gian chờ tối đa, tăng khung giờ chơi hoặc cho phép chơi ngoài trời để tôi lập lại lịch nhé!"
            )
            yield f"event: token\ndata: {json.dumps({'token': accumulated_reply}, ensure_ascii=False)}\n\n"

        add_message(session_id, turn_id, "assistant", accumulated_reply)
        record_event(
            session_id=session_id,
            turn_id=turn_id,
            event_type="a1_result",
            sender="A1",
            receiver="A0",
            summary=f"A1 báo cáo không có phương án khả thi ({len(unfeasible_reasons)} ràng buộc nghẽn).",
            payload=plan_result,
            duration_ms=a1_duration,
            status="warning",
        )
        yield f"event: done\ndata: {json.dumps({'session_id': session_id, 'turn_id': turn_id, 'status': 'no_feasible_plan', 'reply': accumulated_reply, 'plans': [], 'unfeasible_reasons': unfeasible_reasons, 'events': get_events(session_id)}, ensure_ascii=False)}\n\n"
        return

    save_plans(session_id, turn_id, plans)
    record_event(
        session_id=session_id,
        turn_id=turn_id,
        event_type="a1_result",
        sender="A1",
        receiver="A0",
        summary=f"A1 đã lập và kiểm tra thành công {len(plans)} phương án lịch trình qua Validator xác định.",
        payload={
            "plan_result_id": plan_result.get("plan_result_id"),
            "plans_summary": [
                {
                    "style": p["style"],
                    "duration": p["total_duration_minutes"],
                    "buffer": p["end_buffer_minutes"],
                    "services": p["service_ids"],
                }
                for p in plans
            ],
        },
        duration_ms=a1_duration,
        status="success",
    )

    # 6. A0 tổng hợp câu trả lời qua Stream
    yield f"event: thinking\ndata: {json.dumps({'stage': 'a0_synthesize', 'message': 'Agent A0 đang tổng hợp phương án lịch trình chi tiết cho bạn...'}, ensure_ascii=False)}\n\n"
    accumulated_reply = ""
    try:
        for token in stream_synthesize_chat_response_with_llm(user_message, plans, crowd_analysis):
            accumulated_reply += token
            yield f"event: token\ndata: {json.dumps({'token': token}, ensure_ascii=False)}\n\n"
    except Exception as e:
        logger.warning("Stream synthesis error: %s", e)

    if not accumulated_reply:
        reply_lines = [
            f"Dạ, V-AI đã thiết lập {len(plans)} phương án tối ưu cho đoàn của bạn:\n\n"
        ]
        for idx, p in enumerate(plans, 1):
            reply_lines.append(
                f"### {p['style_label']}\n"
                f"- **Lộ trình:** {' ➔ '.join(leg['service_name'] for leg in p['legs'])}\n"
                f"- **Tổng thời gian dự kiến:** **{p['total_duration_minutes']} phút** (kết thúc lúc {p['return_arrival_time']})\n"
                f"- **Thời gian dự phòng trước 16:00:** **{p['end_buffer_minutes']} phút**\n"
                f"- **Tổng chi phí đoàn:** **{p['total_cost_vnd']:,} VNĐ**\n"
                f"- **Lý do:** {p['rationale']}\n"
            )
        reply_lines.append("\nQuý khách có thể xem chi tiết từng chặng ở thẻ bên dưới hoặc tiếp tục chat để điều chỉnh!")
        accumulated_reply = "\n".join(reply_lines)
        yield f"event: token\ndata: {json.dumps({'token': accumulated_reply}, ensure_ascii=False)}\n\n"

    add_message(session_id, turn_id, "assistant", accumulated_reply)
    total_turn_duration = int((time.time() - start_turn_time) * 1000)
    record_event(
        session_id=session_id,
        turn_id=turn_id,
        event_type="a0_reply",
        sender="A0",
        receiver="User",
        summary=f"A0 hoàn thành lượt hội thoại, trình bày {len(plans)} phương án cho khách qua Stream.",
        payload={"plans_count": len(plans), "total_turn_ms": total_turn_duration},
        duration_ms=total_turn_duration,
        status="success",
    )

    yield f"event: done\ndata: {json.dumps({'session_id': session_id, 'turn_id': turn_id, 'status': 'completed', 'reply': accumulated_reply, 'plans': plans, 'crowd_analysis': crowd_analysis, 'events': get_events(session_id)}, ensure_ascii=False)}\n\n"
