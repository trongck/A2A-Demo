"""
Hợp đồng dữ liệu Pydantic chuẩn hóa cho hệ thống V-AI Multi-Agent.
Bám sát mục 4 và mục 7 của V-AI-Implementation-Plan.md.
"""

from typing import Any, Literal
from pydantic import BaseModel, Field


# --- Cấu trúc thành viên nhóm & Ràng buộc ---

class GroupMember(BaseModel):
    member_id: str
    age_years: int
    height_cm: int
    weight_kg: float | None = None


class HardConstraints(BaseModel):
    indoor_only: bool = False
    max_thrill_level: Literal["low", "moderate", "high", "extreme"] = "moderate"
    max_wait_minutes_per_stop: int = 20
    budget_vnd_total: int = 150000
    min_end_buffer_minutes: int = 10
    allow_unknown_crowd: bool = False
    excluded_service_ids: list[str] = Field(default_factory=list)
    min_activity_count: int = 3


class Preferences(BaseModel):
    prioritize_low_crowd: bool = True
    meal_required: bool = False
    plan_styles: list[str] = Field(default_factory=lambda: ["gentle", "more_rides"])


class AlternativeRule(BaseModel):
    minimum_different_service_ids: int = 1
    comparison: str = "at least one selected service in each alternative differs; reordering alone does not count"


class NormalizedRequest(BaseModel):
    request_id: str
    session_id: str
    message: str
    start_at: str  # ISO8601 (ví dụ "2026-09-18T14:00:00+07:00")
    end_by: str    # ISO8601 (ví dụ "2026-09-18T16:00:00+07:00")
    start_node_id: str = "start_sea_hub"
    end_node_id: str = "start_sea_hub"
    group_members: list[GroupMember] = Field(default_factory=list)
    hard_constraints: HardConstraints = Field(default_factory=HardConstraints)
    preferences: Preferences = Field(default_factory=Preferences)
    number_of_plans: int = 2
    alternative_rule: AlternativeRule = Field(default_factory=AlternativeRule)


# --- Hợp đồng giao tiếp Agent (A2A Business Payload) ---

class MemoryRef(BaseModel):
    session_id: str
    version: int


class AgentRequest(BaseModel):
    schema_version: str = "1.0"
    session_id: str
    turn_id: str
    request_id: str
    action: str  # "analyze_crowd", "create_plans"
    memory_ref: MemoryRef
    scenario_id: str = "base"
    data_revision: str = "v1"
    input: dict[str, Any] = Field(default_factory=dict)


class AgentResult(BaseModel):
    schema_version: str = "1.0"
    session_id: str
    turn_id: str
    request_id: str
    action: str
    status: Literal["completed", "needs_input", "no_feasible_plan", "failed"]
    input_memory_version: int
    data_revision: str
    result: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


# --- Kết quả phân tích mật độ A2 ---

class CrowdAnalysisItem(BaseModel):
    service_id: str
    name: str
    zone_id: str
    indoor: bool
    current_people: int | None = None
    queue_people: int | None = None
    wait_minutes: int | None = None
    wait_basis: str
    data_quality: str
    operating_status: str
    status_reason: str | None = None
    comfort_capacity_people: int | None = None
    area_m2: float | None = None
    occupancy_ratio: float | None = None
    density_people_per_m2: float | None = None
    load_category: Literal["low", "medium", "high", "overloaded", "unknown"]
    is_stale: bool = False
    snapshot_timestamp: str | None = None


class CrowdAnalysis(BaseModel):
    analysis_id: str
    simulation_now: str
    scenario_id: str
    data_revision: str
    items: list[CrowdAnalysisItem] = Field(default_factory=list)


# --- Kết quả lập lịch A1 ---

class PlanLeg(BaseModel):
    step: int
    service_id: str
    service_name: str
    node_id: str
    arrival_time: str
    start_time: str
    end_time: str
    walk_from_prev_minutes: int
    wait_minutes: int
    activity_duration_minutes: int
    cost_vnd: int
    indoor: bool
    note: str = ""


class PlanOption(BaseModel):
    plan_id: str
    style: str  # "gentle" hoặc "more_rides" hoặc "indoor"
    style_label: str
    total_duration_minutes: int
    end_buffer_minutes: int
    total_cost_vnd: int
    start_node_id: str
    end_node_id: str
    return_arrival_time: str
    legs: list[PlanLeg] = Field(default_factory=list)
    service_ids: list[str] = Field(default_factory=list)
    rationale: str
    is_feasible: bool = True
    constraint_report: dict[str, Any] = Field(default_factory=dict)


class PlanResult(BaseModel):
    plan_result_id: str
    crowd_analysis_id: str
    scenario_id: str
    data_revision: str
    status: Literal["completed", "no_feasible_plan", "failed"]
    plans: list[PlanOption] = Field(default_factory=list)
    unfeasible_reasons: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


# --- Bảng ghi sự kiện (Events log) ---

class EventRecord(BaseModel):
    event_id: str
    session_id: str
    turn_id: str
    timestamp: str
    event_type: str  # "user_message", "a0_intent", "a0_call_a2", "a2_call_mcp", "a2_result", "a0_call_a1", "a1_call_mcp", "a1_result", "a0_reply", "error"
    sender: str
    receiver: str
    summary: str
    payload: dict[str, Any] = Field(default_factory=dict)
    duration_ms: int = 0
    status: Literal["success", "warning", "error", "info"] = "info"
