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
from typing import Any

import httpx

from shared.llm import (
    answer_general_chat_with_llm,
    classify_and_extract_intent_with_llm,
    generate_clarification_with_llm,
    generate_unfeasible_explanation_with_llm,
    is_llm_available,
    synthesize_chat_response_with_llm,
)
from shared.memory.database import (
    add_message,
    get_or_create_session,
    record_event,
    save_agent_result,
    save_plans,
    update_session,
)


A2_URL = "http://127.0.0.1:8002"
A1_URL = "http://127.0.0.1:8001"



def call_a2a_agent(agent_url: str, request_payload: dict[str, Any]) -> dict[str, Any]:
    """Gọi Specialist Agent qua giao thức A2A JSON-RPC / HTTP."""
    # Gọi qua endpoint trực tiếp nếu có hoặc qua JSON-RPC message
    target_action = request_payload.get("action")
    endpoint = f"{agent_url}/api/analyze" if target_action == "analyze_crowd" else f"{agent_url}/api/plan"

    try:
        with httpx.Client(timeout=15.0) as client:
            if target_action == "analyze_crowd":
                resp = client.post(
                    endpoint,
                    json={
                        "scenario_id": request_payload.get("scenario_id", "base"),
                        "service_ids": request_payload.get("input", {}).get("service_ids"),
                    },
                )
            else:
                resp = client.post(
                    endpoint,
                    json={
                        "normalized_request": request_payload.get("input", {}).get("normalized_request", {}),
                        "crowd_analysis": request_payload.get("input", {}).get("crowd_analysis", {}),
                        "scenario_id": request_payload.get("scenario_id", "base"),
                    },
                )

            if resp.status_code == 200:
                return {
                    "status": "completed",
                    "result": resp.json(),
                }
    except Exception as e:
        # Fallback local import khi chạy in-process hoặc test
        if target_action == "analyze_crowd":
            from agents.a2.server import analyze_crowd_logic
            res = analyze_crowd_logic(
                scenario_id=request_payload.get("scenario_id", "base"),
                service_ids=request_payload.get("input", {}).get("service_ids"),
            )
            return {"status": "completed", "result": res}
        else:
            from agents.a1.server import plan_itinerary_logic
            res = plan_itinerary_logic(
                normalized_request=request_payload.get("input", {}).get("normalized_request", {}),
                crowd_analysis=request_payload.get("input", {}).get("crowd_analysis", {}),
                scenario_id=request_payload.get("scenario_id", "base"),
            )
            return {"status": res.get("status", "completed"), "result": res}

    return {"status": "failed", "error": f"Không thể kết nối đến {agent_url}"}


def extract_or_update_request(
    user_message: str,
    current_session: dict[str, Any],
    preset_data: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], bool, list[str], str]:
    """Trích xuất và chuẩn hóa yêu cầu của người dùng kết hợp LLM và quy tắc logic."""
    profile = copy.deepcopy(current_session.get("profile", {}))
    missing_fields = []

    # Nếu người dùng nạp từ preset (ví dụ preset gia đình)
    if preset_data:
        profile.update(preset_data)

    intent_type = "plan_itinerary"

    # 1. Thử phân loại intent và trích xuất thực thể qua LLM
    if is_llm_available():
        try:
            llm_result = classify_and_extract_intent_with_llm(user_message, profile)
            intent_type = llm_result.get("intent", "plan_itinerary")
            entities = llm_result.get("entities", {})

            if entities.get("indoor_only") is not None:
                profile.setdefault("hard_constraints", {})["indoor_only"] = entities["indoor_only"]
            if entities.get("min_activity_count") is not None:
                profile.setdefault("hard_constraints", {})["min_activity_count"] = entities["min_activity_count"]
            if entities.get("max_wait_minutes") is not None:
                profile.setdefault("hard_constraints", {})["max_wait_minutes_per_stop"] = entities["max_wait_minutes"]

            if entities.get("height_cm") is not None:
                h = int(entities["height_cm"])
                if not profile.get("group_members"):
                    profile["group_members"] = [
                        {"member_id": "adult_1", "age_years": 32, "height_cm": 170},
                        {"member_id": "child_1", "age_years": 10, "height_cm": h},
                    ]
                else:
                    for m in profile["group_members"]:
                        if "child" in m.get("member_id", "") or m.get("age_years", 0) < 18:
                            m["height_cm"] = h

            if entities.get("time_hours") is not None:
                hours = float(entities["time_hours"])
                profile["start_at"] = "2026-09-18T14:00:00+07:00"
                end_hour = 14 + int(hours)
                end_min = int((hours - int(hours)) * 60)
                profile["end_by"] = f"2026-09-18T{end_hour:02d}:{end_min:02d}:00+07:00"

            if entities.get("start_time"):
                st = str(entities["start_time"]).strip()
                if len(st) == 5 and ":" in st:
                    profile["start_at"] = f"2026-09-18T{st}:00+07:00"

            if entities.get("end_time"):
                et = str(entities["end_time"]).strip()
                if len(et) == 5 and ":" in et:
                    profile["end_by"] = f"2026-09-18T{et}:00+07:00"

        except Exception as e:
            print(f"[Agent A0] LLM intent error: {e}")

    # 2. Xử lý logic quy tắc bổ trợ
    msg_lower = user_message.lower()

    planning_keywords = [
        "gợi ý", "lập lịch", "lên lịch", "lịch trình", "kế hoạch", "chơi gì",
        "trò chơi", "điểm chơi", "tham quan", "tư vấn", "lộ trình",
    ]
    if any(k in msg_lower for k in planning_keywords):
        intent_type = "plan_itinerary"

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

    # Nếu chưa có thông tin thành viên
    if not profile.get("group_members"):
        match_height = re.search(r"cao\s+(\d+)\s*cm", msg_lower)
        if match_height:
            h = int(match_height.group(1))
            profile["group_members"] = [
                {"member_id": "adult_1", "age_years": 32, "height_cm": 170},
                {"member_id": "child_1", "age_years": 10, "height_cm": h},
            ]
        elif intent_type != "general_chat":
            missing_fields.append("chiều_cao_trẻ_em")

    if not profile.get("start_at") or not profile.get("end_by"):
        match_time = re.search(r"(\d{1,2})\s*tiếng|(\d{1,2})\s*giờ", msg_lower)
        if match_time:
            profile["start_at"] = "2026-09-18T14:00:00+07:00"
            profile["end_by"] = "2026-09-18T16:00:00+07:00"
        elif not profile.get("start_at") and intent_type != "general_chat":
            missing_fields.append("khung_giờ_tham_quan")

    # Mặc định các thông số tiêu chuẩn nếu chưa có
    profile.setdefault("start_node_id", "start_sea_hub")
    profile.setdefault("end_node_id", "start_sea_hub")
    profile.setdefault("number_of_plans", 2)
    profile.setdefault("hard_constraints", {
        "indoor_only": False,
        "max_thrill_level": "moderate",
        "max_wait_minutes_per_stop": 20,
        "budget_vnd_total": 150000,
        "min_end_buffer_minutes": 10,
        "allow_unknown_crowd": False,
        "excluded_service_ids": [],
        "min_activity_count": 3,
    })
    profile.setdefault("preferences", {
        "prioritize_low_crowd": True,
        "meal_required": False,
        "plan_styles": ["gentle", "more_rides"],
    })

    is_complete = len(missing_fields) == 0 and intent_type != "general_chat"
    return profile, is_complete, missing_fields, intent_type



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

    # 2. Phân loại yêu cầu & Chuẩn hóa dữ liệu
    t_start = time.time()
    updated_profile, is_complete, missing_fields, intent_type = extract_or_update_request(
        user_message=user_message,
        current_session=session,
        preset_data=preset_data,
    )
    extract_duration = int((time.time() - t_start) * 1000)

    # 3a. Nếu là General Chat (chào hỏi, hỏi thông tin công viên)
    if intent_type == "general_chat":
        t_chat = time.time()
        chat_reply = answer_general_chat_with_llm(user_message)
        if not chat_reply:
            chat_reply = (
                "Xin chào bạn! Tôi là Hướng dẫn viên ảo kiêm Điều phối viên hệ thống V-AI tại VinWonders Nha Trang. "
                "Tôi có thể hỗ trợ bạn thông tin về các phân khu vui chơi và phối hợp cùng Chuyên gia Mật độ (A2) "
                "và Chuyên gia Lập lịch (A1) để lên kế hoạch trải nghiệm tối ưu cho cả đoàn. "
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
        }

    # 3b. Xử lý trường hợp thiếu thông tin bắt buộc khi lập lịch
    if not is_complete:
        t_clarify = time.time()
        clarification_msg = None
        if is_llm_available():
            try:
                clarification_msg = generate_clarification_with_llm(user_message, missing_fields)
            except Exception as e:
                print(f"[Agent A0] LLM clarification error: {e}")

        if not clarification_msg:
            clarification_msg = (
                "Chào bạn! Để tôi có thể gợi ý lịch trình vui chơi VinWonders an toàn và phù hợp nhất cho cả đoàn, "
                f"bạn vui lòng cho biết thêm: {', '.join(missing_fields).replace('_', ' ')} nhé!"
            )
        clarify_duration = int((time.time() - t_clarify) * 1000)
        add_message(session_id, turn_id, "assistant", clarification_msg)
        record_event(
            session_id=session_id,
            turn_id=turn_id,
            event_type="a0_intent",
            sender="A0",
            receiver="User",
            summary=f"Yêu cầu thiếu dữ liệu: {missing_fields}. A0 hỏi làm rõ bằng LLM.",
            payload={"missing_fields": missing_fields, "response": clarification_msg},
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
        "data_revision": "v1",
        "input": {"service_ids": None},
    }

    a2_resp = call_a2a_agent(A2_URL, a2_req)
    a2_duration = int((time.time() - t_a2) * 1000)

    if a2_resp.get("status") != "completed":
        err_msg = f"Agent A2 gặp lỗi khi phân tích: {a2_resp.get('error', 'Lỗi không xác định')}"
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
        "data_revision": "v1",
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
                print(f"[Agent A0] LLM unfeasible error: {e}")

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
            print(f"[Agent A0] LLM synthesis error: {e}")

    if llm_reply:
        full_reply = llm_reply
    else:

        reply_lines = [
            f"Dạ, Agent A0 đã phối hợp cùng Agent A2 (Phân tích mật độ) và Agent A1 (Lập lịch trình) để thiết lập {len(plans)} phương án tối ưu cho đoàn của bạn:\n"
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
    }
