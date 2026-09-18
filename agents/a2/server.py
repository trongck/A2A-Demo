"""
Agent A2: Crowd Specialist.
Chạy trên cổng 8002.
A2A Server cung cấp Agent Card và Skill phân tích mật độ.
Bám sát mục 4 và mục 7 của V-AI-Implementation-Plan.md.
"""

import json
import time
import uuid
from datetime import datetime
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
from shared.llm import generate_crowd_insight_with_llm, is_llm_available

MCP_URL = "http://127.0.0.1:8003"



def call_mcp_tool(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Gọi công cụ qua MCP Server HTTP endpoint với caller_agent=a2_crowd_specialist."""
    try:
        with httpx.Client(timeout=3.0) as client:
            resp = client.post(
                f"{MCP_URL}/api/tools/call",
                json={
                    "tool_name": tool_name,
                    "arguments": arguments,
                    "caller_agent": "a2_crowd_specialist",
                },
            )
            if resp.status_code == 200:
                return resp.json().get("result", {})
    except Exception:
        pass


    # Fallback trực tiếp tới mcp_server module khi chưa bật process 8003
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



def analyze_crowd_logic(
    scenario_id: str = "base",
    service_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Thực thi logic phân tích mật độ, tỷ lệ tải, kiểm tra độ mới và trạng thái vận hành."""
    # 1. Đọc dữ liệu từ MCP Server
    attractions = call_mcp_tool("get_attractions", {"scenario_id": scenario_id, "service_ids": service_ids})
    crowd_data = call_mcp_tool("get_crowd_snapshots", {"scenario_id": scenario_id, "service_ids": service_ids})

    simulation_now_str = crowd_data.get("simulation_now", "2026-09-18T14:00:00+07:00")
    sim_now = datetime.fromisoformat(simulation_now_str)
    freshness_limit_sec = crowd_data.get("config", {}).get("freshness_seconds", 180)
    thresholds = crowd_data.get("config", {}).get("crowd_thresholds", {"low_lt": 0.4, "medium_lt": 0.7, "high_lt": 1.0})

    snapshots = {s["service_id"]: s for s in crowd_data.get("snapshots", [])}

    items = []
    warnings = []
    errors = []

    for attr in attractions:
        sid = attr["service_id"]
        name = attr.get("name", sid)
        zone_id = attr.get("zone_id", "")
        indoor = attr.get("indoor", False)

        snap = snapshots.get(sid)
        if not snap:
            warnings.append(f"Không tìm thấy snapshot mật độ cho {sid} ({name})")
            continue

        operating_status = snap.get("operating_status", "open")
        status_reason = snap.get("status_reason")
        data_quality = snap.get("data_quality", "valid")
        observed_at_str = snap.get("observed_at")
        wait_basis = snap.get("wait_basis", "unknown")

        current_people = snap.get("current_people")
        queue_people = snap.get("queue_people")
        wait_minutes = snap.get("wait_minutes")

        # Kiểm tra độ mới (freshness)
        is_stale = False
        if observed_at_str:
            try:
                obs_dt = datetime.fromisoformat(observed_at_str)
                age_sec = (sim_now - obs_dt).total_seconds()
                if age_sec > freshness_limit_sec:
                    is_stale = True
                    warnings.append(f"Snapshot của {sid} ({name}) đã cũ ({age_sec:.0f}s > {freshness_limit_sec}s)")
            except Exception as e:
                is_stale = True
                warnings.append(f"Không thể đọc timestamp của {sid}: {e}")

        # Kiểm tra sức chứa vùng đếm
        crowd_ref = attr.get("crowd_reference", {})
        comfort_cap = crowd_ref.get("comfort_capacity_people")
        area_m2 = crowd_ref.get("area_m2")

        occupancy_ratio = None
        density_m2 = None
        load_category = "unknown"

        if operating_status == "temporarily_closed":
            load_category = "unknown"
            wait_minutes = None
        elif current_people is not None:
            # Tính occupancy_ratio
            if comfort_cap is None or comfort_cap <= 0:
                errors.append(f"Mẫu số comfort_capacity_people không hợp lệ cho {sid}")
            else:
                occupancy_ratio = round(current_people / comfort_cap, 3)

            # Tính density_people_per_m2
            if area_m2 is not None and area_m2 > 0:
                density_m2 = round(current_people / area_m2, 3)

            # Phân loại tải
            if occupancy_ratio is not None:
                if occupancy_ratio < thresholds.get("low_lt", 0.4):
                    load_category = "low"
                elif occupancy_ratio < thresholds.get("medium_lt", 0.7):
                    load_category = "medium"
                elif occupancy_ratio < thresholds.get("high_lt", 1.0):
                    load_category = "high"
                else:
                    load_category = "overloaded"
        else:
            # current_people is null: tuyệt đối không đổi thành 0
            load_category = "unknown"

        items.append({
            "service_id": sid,
            "name": name,
            "zone_id": zone_id,
            "indoor": indoor,
            "current_people": current_people,
            "queue_people": queue_people,
            "wait_minutes": wait_minutes,
            "wait_basis": wait_basis,
            "data_quality": data_quality,
            "operating_status": operating_status,
            "status_reason": status_reason,
            "comfort_capacity_people": comfort_cap,
            "area_m2": area_m2,
            "occupancy_ratio": occupancy_ratio,
            "density_people_per_m2": density_m2,
            "load_category": load_category,
            "is_stale": is_stale,
            "snapshot_timestamp": observed_at_str,
        })

    # 2. Sinh nhận định phân tích mật độ chuyên môn bằng LLM (hoặc fallback nếu LLM không khả dụng)
    crowd_insight_text = None
    if is_llm_available():
        try:
            crowd_insight_text = generate_crowd_insight_with_llm(items, simulation_now_str, scenario_id)
        except Exception as e:
            print(f"[Agent A2] Lỗi gọi LLM phân tích mật độ: {e}")

    if not crowd_insight_text:
        # Fallback phân tích dựa trên quy tắc thống kê
        high_wait = [it for it in items if (it.get("wait_minutes") or 0) >= 20 or it.get("load_category") in ("high", "overloaded")]
        low_wait = [it for it in items if (it.get("wait_minutes") or 0) <= 10 and it.get("operating_status") == "open"]
        high_names = ", ".join(it["name"] for it in high_wait[:3]) if high_wait else "không có điểm nào"
        low_names = ", ".join(it["name"] for it in low_wait[:3]) if low_wait else "các khu vực tiêu chuẩn"
        crowd_insight_text = (
            f"Vào thời điểm {simulation_now_str.split('T')[1][:5]}, công viên hoạt động ổn định. "
            f"Điểm nóng có hàng chờ cao gồm: {high_names}. "
            f"Khuyến nghị ưu tiên điều hướng khách qua các điểm thông thoáng: {low_names}."
        )

    analysis_id = f"analysis_{uuid.uuid4().hex[:8]}"
    return {
        "analysis_id": analysis_id,
        "simulation_now": simulation_now_str,
        "scenario_id": scenario_id,
        "data_revision": "v1",
        "items": items,
        "crowd_insights": crowd_insight_text,
        "warnings": warnings,
        "errors": errors,
    }



# --- A2A Executor & Application ---

class CrowdSpecialistExecutor(AgentExecutor):
    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        raw_text = ""
        if context.message and context.message.parts:
            raw_text = context.message.parts[0].text

        try:
            req_data = json.loads(raw_text) if raw_text else {}
        except Exception:
            req_data = {}

        scenario_id = req_data.get("scenario_id", "base")
        session_id = req_data.get("session_id", "default_session")
        turn_id = req_data.get("turn_id", "turn_001")
        request_id = req_data.get("request_id", "req_a2_001")
        input_data = req_data.get("input", {})
        service_ids = input_data.get("service_ids")

        analysis = analyze_crowd_logic(scenario_id=scenario_id, service_ids=service_ids)

        agent_result = {
            "schema_version": "1.0",
            "session_id": session_id,
            "turn_id": turn_id,
            "request_id": request_id,
            "action": "analyze_crowd",
            "status": "completed" if not analysis.get("errors") else "failed",
            "input_memory_version": req_data.get("memory_ref", {}).get("version", 1),
            "data_revision": req_data.get("data_revision", "v1"),
            "result": analysis,
            "warnings": analysis.get("warnings", []),
            "errors": analysis.get("errors", []),
        }

        reply_msg = Message(
            role=Role.assistant,
            parts=[TextPart(text=json.dumps(agent_result, ensure_ascii=False))],
        )
        await event_queue.enqueue_event(reply_msg)

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        pass


agent_card = AgentCard(
    name="a2_crowd_specialist",
    description="Agent chuyên gia phân tích mật độ, thời gian chờ và tình trạng tải VinWonders",
    version="1.0.0",
    url="http://127.0.0.1:8002",
    capabilities=AgentCapabilities(),
    default_input_modes=["text"],
    default_output_modes=["text"],
    skills=[
        AgentSkill(
            id="analyze_crowd",
            name="Phân tích mật độ",
            description="Phân tích dữ liệu đếm người, tỷ lệ tải, hàng chờ và cảnh báo dữ liệu cũ",
            tags=["crowd", "analytics"],
        )
    ],
)

handler = DefaultRequestHandler(
    agent_executor=CrowdSpecialistExecutor(),
    task_store=InMemoryTaskStore(),
)

app_builder = A2AFastAPIApplication(agent_card=agent_card, http_handler=handler)
app = app_builder.build()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "agent": "a2_crowd_specialist", "port": "8002"}


class DirectAnalyzeRequest(BaseModel):
    scenario_id: str = "base"
    service_ids: list[str] | None = None


@app.post("/api/analyze")
def direct_analyze(req: DirectAnalyzeRequest) -> dict[str, Any]:
    return analyze_crowd_logic(scenario_id=req.scenario_id, service_ids=req.service_ids)


if __name__ == "__main__":
    print("Khởi động Agent A2 (Crowd Specialist) tại http://127.0.0.1:8002...")
    uvicorn.run(app, host="127.0.0.1", port=8002, log_level="info")
