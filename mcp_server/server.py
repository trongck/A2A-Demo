"""
MCP Server cho hệ thống V-AI.
Chạy trên cổng 8003.
Cung cấp 4 tools:
1. get_attractions
2. get_crowd_snapshots
3. get_route_matrix
4. get_weather
Bám sát mục 5 của V-AI-Implementation-Plan.md.
"""

import copy
import heapq
import json
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn
from mcp.server.mcpserver import MCPServer

from shared.security import (
    ALLOWED_ORIGINS,
    SecurityHeadersMiddleware,
    get_logger,
    require_internal_secret,
)

logger = get_logger("mcp.server")

DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "V-AI-Mock-Data.json"

# --- Khởi tạo và đọc dữ liệu ---

def load_data() -> dict[str, Any]:
    if not DATA_PATH.exists():
        raise FileNotFoundError(f"Không tìm thấy file dữ liệu tại {DATA_PATH}")
    with open(DATA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


# --- Thuật toán tìm đường ngắn nhất Dijkstra ---

def compute_shortest_paths(edges_data: list[dict[str, Any]], nodes: list[str]) -> dict[str, dict[str, Any]]:
    """Tính đường đi ngắn nhất giữa các node bằng Dijkstra trên đồ thị có hướng/vô hướng."""
    adj: dict[str, list[tuple[str, int, str]]] = {}
    for e in edges_data:
        if not e.get("is_open", True):
            continue
        u = e["from_node_id"]
        v = e["to_node_id"]
        w = int(e.get("walking_minutes", 0))
        eid = e.get("edge_id", "")
        adj.setdefault(u, []).append((v, w, eid))
        if e.get("bidirectional", False):
            adj.setdefault(v, []).append((u, w, eid))

    matrix: dict[str, dict[str, Any]] = {}
    for start in nodes:
        dist: dict[str, int] = {start: 0}
        prev: dict[str, tuple[str | None, str | None]] = {start: (None, None)}
        pq: list[tuple[int, str]] = [(0, start)]
        visited: set[str] = set()

        while pq:
            d, u = heapq.heappop(pq)
            if u in visited:
                continue
            visited.add(u)

            for v, w, eid in adj.get(u, []):
                new_d = d + w
                if new_d < dist.get(v, float("inf")):
                    dist[v] = new_d
                    prev[v] = (u, eid)
                    heapq.heappush(pq, (new_d, v))

        matrix[start] = {}
        for target in nodes:
            if target in dist:
                # Reconstruct path
                curr = target
                path = []
                while curr is not None:
                    path.append(curr)
                    p_node, _ = prev.get(curr, (None, None))
                    curr = p_node
                path.reverse()
                matrix[start][target] = {
                    "walking_minutes": dist[target],
                    "path": path,
                    "reachable": True,
                }
            else:
                matrix[start][target] = {
                    "walking_minutes": None,
                    "path": [],
                    "reachable": False,
                }
    return matrix


# --- Core Tool Implementations ---

def tool_get_attractions(scenario_id: str = "base", service_ids: list[str] | None = None) -> list[dict[str, Any]]:
    data = load_data()
    attractions = data.get("attractions", [])
    if service_ids:
        s_set = set(service_ids)
        attractions = [a for a in attractions if a.get("service_id") in s_set]
    return attractions


def tool_get_crowd_snapshots(scenario_id: str = "base", service_ids: list[str] | None = None) -> dict[str, Any]:
    data = load_data()
    snapshots = copy.deepcopy(data.get("crowd_snapshots", []))
    simulation_now = data.get("simulation_now", "2026-09-18T14:00:00+07:00")
    config = data.get("config", {})

    # Áp dụng scenario overrides nếu có
    test_scenarios = data.get("test_scenarios", [])
    matching_scenario = next((s for s in test_scenarios if s.get("scenario_id") == scenario_id), None)
    if matching_scenario and "snapshot_overrides" in matching_scenario:
        overrides = {o["service_id"]: o for o in matching_scenario["snapshot_overrides"]}
        for snap in snapshots:
            sid = snap.get("service_id")
            if sid in overrides:
                # Cập nhật snapshot theo override
                snap.update(overrides[sid])

    if service_ids:
        s_set = set(service_ids)
        snapshots = [s for s in snapshots if s.get("service_id") in s_set]

    return {
        "scenario_id": scenario_id,
        "simulation_now": simulation_now,
        "config": config,
        "snapshots": snapshots,
    }


def tool_get_route_matrix(node_ids: list[str]) -> dict[str, Any]:
    data = load_data()
    edges = data.get("routing", {}).get("edges", [])
    all_nodes = [n["node_id"] for n in data.get("routing", {}).get("nodes", [])]
    target_nodes = list(set(node_ids if node_ids else all_nodes))
    matrix = compute_shortest_paths(edges, target_nodes)
    return {
        "map_id": data.get("routing", {}).get("map_id", "vinwonders_nha_trang_mock_map"),
        "matrix": matrix,
    }


def tool_get_weather(start_at: str, end_by: str) -> dict[str, Any]:
    data = load_data()
    windows = data.get("environment", {}).get("weather_windows", [])
    return {
        "forecast_issued_at": data.get("environment", {}).get("forecast_issued_at", ""),
        "query_range": {"start_at": start_at, "end_by": end_by},
        "weather_windows": windows,
    }


# --- Khởi tạo MCP Server ---

mcp = MCPServer("v-ai-mcp-server")


@mcp.tool()
def get_attractions(scenario_id: str = "base", service_ids: list[str] | None = None) -> str:
    """Lấy thông tin danh mục trò chơi, điểm tham quan, quy định chiều cao và giá vé."""
    result = tool_get_attractions(scenario_id, service_ids)
    return json.dumps(result, ensure_ascii=False)


@mcp.tool()
def get_crowd_snapshots(scenario_id: str = "base", service_ids: list[str] | None = None) -> str:
    """Lấy thông tin mật độ hiện tại, số người xếp hàng, thời gian chờ và trạng thái camera."""
    result = tool_get_crowd_snapshots(scenario_id, service_ids)
    return json.dumps(result, ensure_ascii=False)


@mcp.tool()
def get_route_matrix(node_ids: list[str]) -> str:
    """Tính ma trận thời gian đi bộ và đường đi ngắn nhất giữa các điểm."""
    result = tool_get_route_matrix(node_ids)
    return json.dumps(result, ensure_ascii=False)


@mcp.tool()
def get_weather(start_at: str, end_by: str) -> str:
    """Lấy thông tin thời tiết và khả năng hoạt động ngoài trời trong khung giờ."""
    result = tool_get_weather(start_at, end_by)
    return json.dumps(result, ensure_ascii=False)


# --- FastAPI REST Wrapper & Health Endpoints ---

app = FastAPI(title="V-AI MCP Service", version="1.0.0")

app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,  # C2: Whitelist thay vì "*"
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "X-Internal-Secret"],
)


TOOL_PERMISSIONS = {
    "get_attractions": {"a1_planner_specialist", "a2_crowd_specialist"},
    "get_crowd_snapshots": {"a2_crowd_specialist"},
    "get_route_matrix": {"a1_planner_specialist"},
    "get_weather": {"a1_planner_specialist"},
}


class ToolCallRequest(BaseModel):
    tool_name: str
    arguments: dict[str, Any] = {}
    caller_agent: str = "anonymous"


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok", "service": "mcp_server", "port": "8003"}


@app.get("/api/tools/list")
def list_tools() -> list[dict[str, Any]]:
    return [
        {"name": "get_attractions", "allowed_callers": list(TOOL_PERMISSIONS["get_attractions"]), "description": "Lấy thông tin danh mục trò chơi"},
        {"name": "get_crowd_snapshots", "allowed_callers": list(TOOL_PERMISSIONS["get_crowd_snapshots"]), "description": "Lấy thông tin mật độ và hàng chờ"},
        {"name": "get_route_matrix", "allowed_callers": list(TOOL_PERMISSIONS["get_route_matrix"]), "description": "Tính ma trận đường đi ngắn nhất"},
        {"name": "get_weather", "allowed_callers": list(TOOL_PERMISSIONS["get_weather"]), "description": "Lấy thông tin thời tiết"},
    ]


@app.post("/api/tools/call", dependencies=[Depends(require_internal_secret)])
def call_tool_endpoint(req: ToolCallRequest) -> dict[str, Any]:
    name = req.tool_name
    args = req.arguments
    caller = req.caller_agent

    allowed = TOOL_PERMISSIONS.get(name, set())
    if caller not in allowed:
        raise HTTPException(
            status_code=403,
            detail=f"Truy cập bị từ chối: Agent '{caller}' không có quyền gọi công cụ '{name}'. Quyền hạn chỉ dành cho: {list(allowed)}"
        )

    if name == "get_attractions":
        return {"result": tool_get_attractions(args.get("scenario_id", "base"), args.get("service_ids"))}
    elif name == "get_crowd_snapshots":
        return {"result": tool_get_crowd_snapshots(args.get("scenario_id", "base"), args.get("service_ids"))}
    elif name == "get_route_matrix":
        node_ids = args.get("node_ids", [])
        return {"result": tool_get_route_matrix(node_ids)}
    elif name == "get_weather":
        return {"result": tool_get_weather(args.get("start_at", ""), args.get("end_by", ""))}
    else:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy công cụ '{name}'")



if __name__ == "__main__":
    print("Khởi động MCP Server tại http://127.0.0.1:8003...")
    uvicorn.run(app, host="127.0.0.1", port=8003, log_level="info")
