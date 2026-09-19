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

import heapq
import json
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
from shared.data_adapter import DATA_PATH, DATA_REVISION, load_v2_data

logger = get_logger("mcp.server")

# --- Khởi tạo và đọc dữ liệu ---

def load_data(scope: str = "vinwonders") -> dict[str, Any]:
    return load_v2_data(scope)


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

def tool_get_attractions(
    scenario_id: str = "base",
    service_ids: list[str] | None = None,
    categories: list[str] | None = None,
    limit: int | None = None,
    scope: str = "vinwonders",
) -> list[dict[str, Any]]:
    data = load_data(scope)
    attractions = data.get("attractions", [])
    if service_ids:
        s_set = set(service_ids)
        attractions = [a for a in attractions if a.get("service_id") in s_set]
    if categories:
        category_set = set(categories)
        attractions = [a for a in attractions if a.get("category") in category_set]
    return attractions[:limit] if limit else attractions


def tool_get_crowd_snapshots(
    scenario_id: str = "base",
    service_ids: list[str] | None = None,
    scope: str = "vinwonders",
) -> dict[str, Any]:
    data = load_data(scope)
    snapshots = data.get("crowd_snapshots", [])
    simulation_now = data.get("simulation_now")
    config = data.get("config", {})

    if service_ids:
        s_set = set(service_ids)
        snapshots = [s for s in snapshots if s.get("service_id") in s_set]

    return {
        "scenario_id": scenario_id,
        "data_revision": DATA_REVISION,
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
        "data_revision": DATA_REVISION,
        "map_id": data.get("routing", {}).get("map_id", "vinwonders_nha_trang_mock_map"),
        "matrix": matrix,
    }


def tool_get_weather(start_at: str, end_by: str) -> dict[str, Any]:
    data = load_data()
    windows = data.get("environment", {}).get("weather_windows", [])
    return {
        "data_revision": DATA_REVISION,
        "forecast_issued_at": data.get("environment", {}).get("forecast_issued_at", ""),
        "query_range": {"start_at": start_at, "end_by": end_by},
        "weather_windows": windows,
    }


# --- Khởi tạo MCP Server ---

mcp = MCPServer("v-ai-mcp-server")


@mcp.tool()
def get_attractions(
    scenario_id: str = "base",
    service_ids: list[str] | None = None,
    categories: list[str] | None = None,
    limit: int | None = None,
    scope: str = "vinwonders",
) -> str:
    """Lấy địa điểm V2 cùng tọa độ, loại hình, giờ mở cửa, rating và metadata nguồn."""
    result = tool_get_attractions(scenario_id, service_ids, categories, limit, scope)
    return json.dumps(result, ensure_ascii=False)


@mcp.tool()
def get_crowd_snapshots(
    scenario_id: str = "base",
    service_ids: list[str] | None = None,
    scope: str = "vinwonders",
) -> str:
    """Lấy trạng thái crowd V2; trường không có trong nguồn được trả null/unavailable."""
    result = tool_get_crowd_snapshots(scenario_id, service_ids, scope)
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
    return {"status": "ok", "service": "mcp_server", "port": "8003", "data_revision": DATA_REVISION}


@app.get("/api/tools/list")
def list_tools() -> list[dict[str, Any]]:
    return [
        {"name": "get_attractions", "allowed_callers": list(TOOL_PERMISSIONS["get_attractions"]), "description": "Địa điểm V2: tọa độ, loại hình, giờ mở cửa, rating/reviews", "arguments": ["scenario_id", "service_ids", "categories", "limit", "scope"]},
        {"name": "get_crowd_snapshots", "allowed_callers": list(TOOL_PERMISSIONS["get_crowd_snapshots"]), "description": "Trạng thái vận hành; crowd thiếu trong V2 trả null", "arguments": ["scenario_id", "service_ids", "scope"]},
        {"name": "get_route_matrix", "allowed_callers": list(TOOL_PERMISSIONS["get_route_matrix"]), "description": "Ma trận đi bộ ước tính từ tọa độ V2", "arguments": ["node_ids"]},
        {"name": "get_weather", "allowed_callers": list(TOOL_PERMISSIONS["get_weather"]), "description": "Thời tiết; V2 không cung cấp nên có thể rỗng", "arguments": ["start_at", "end_by"]},
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
        return {"result": tool_get_attractions(
            args.get("scenario_id", "base"), args.get("service_ids"), args.get("categories"),
            args.get("limit"), args.get("scope", "vinwonders"),
        )}
    elif name == "get_crowd_snapshots":
        return {"result": tool_get_crowd_snapshots(
            args.get("scenario_id", "base"), args.get("service_ids"), args.get("scope", "vinwonders"),
        )}
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
