"""
agents/a0/admin_server.py
Admin Portal Router — mount vao /admin tren A0 FastAPI app.

Endpoints:
  POST /admin/auth/login
  GET  /admin/auth/me
  GET  /admin/crowd/overview

  GET  /admin/bookings
  GET  /admin/bookings/stats
  GET  /admin/bookings/{session_id}
  POST /admin/bookings/{session_id}/confirm
  POST /admin/bookings/{session_id}/reject

  GET  /admin/map/graph
  GET  /admin/map/path
  GET  /admin/map/plan/{session_id}/{plan_index}
"""

import heapq
import time
from collections import defaultdict
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field

from shared.admin_auth.auth import (
    create_admin_token,
    get_current_admin,
    require_admin_token,
    verify_password,
)
from shared.memory.database import (
    admin_confirm_plan,
    admin_reject_session,
    get_admin_booking_stats,
    get_admin_user,
    get_all_plans_for_session,
    get_all_sessions_summary,
    get_events,
    get_messages,
    get_or_create_session,
    update_admin_last_login,
)
from shared.data_adapter import START_NODE_ID, load_v2_data

admin_router = APIRouter(prefix="/admin", tags=["Admin Portal"])

# ----------------------------------------------------------------- helpers ---

def _load_mock_data() -> dict[str, Any]:
    """Đọc và chuẩn hóa V-AI-Mock-Data-V2.json."""
    return load_v2_data()


def _compute_crowd_level(occupancy_rate: float | None, data_quality: str) -> str:
    if data_quality not in {"valid", "mock"} or occupancy_rate is None:
        return "unknown"
    if occupancy_rate < 0.4:
        return "low"
    if occupancy_rate < 0.7:
        return "medium"
    return "high"


def _dijkstra(nodes: list[dict], edges: list[dict], from_id: str, to_id: str) -> dict[str, Any] | None:
    """
    Dijkstra shortest path tren graph walking_minutes.
    Returns: { path_nodes, total_walking_minutes, total_distance_m } hoac None.
    """
    adj: dict[str, list[tuple[float, int, str]]] = defaultdict(list)
    for e in edges:
        if not e.get("is_open", True):
            continue
        w = e["walking_minutes"]
        d = e.get("distance_m", 0)
        adj[e["from_node_id"]].append((w, d, e["to_node_id"]))
        if e.get("bidirectional"):
            adj[e["to_node_id"]].append((w, d, e["from_node_id"]))

    dist: dict[str, float] = {n["node_id"]: float("inf") for n in nodes}
    dist[from_id] = 0
    dist_m: dict[str, int] = defaultdict(int)
    prev: dict[str, str | None] = {n["node_id"]: None for n in nodes}
    heap: list[tuple[float, str]] = [(0, from_id)]

    while heap:
        cur_d, cur = heapq.heappop(heap)
        if cur_d > dist[cur]:
            continue
        for w, d, nb in adj[cur]:
            nd = cur_d + w
            if nd < dist.get(nb, float("inf")):
                dist[nb] = nd
                dist_m[nb] = dist_m[cur] + d
                prev[nb] = cur
                heapq.heappush(heap, (nd, nb))

    if dist.get(to_id, float("inf")) == float("inf"):
        return None

    # Reconstruct path
    path = []
    cur = to_id
    while cur is not None:
        path.append(cur)
        cur = prev.get(cur)
    path.reverse()

    return {
        "path_nodes": path,
        "total_walking_minutes": dist[to_id],
        "total_distance_m": dist_m[to_id],
    }


# --------------------------------------------------------- rate limit cache ---
_login_attempts: dict[str, list[float]] = defaultdict(list)
_LOGIN_LIMIT = 5
_LOGIN_WINDOW = 60  # seconds
_LOCKOUT_DURATION = 900  # 15 minutes

def _check_rate_limit(ip: str) -> None:
    now = time.time()
    attempts = [t for t in _login_attempts[ip] if now - t < _LOCKOUT_DURATION]
    recent = [t for t in attempts if now - t < _LOGIN_WINDOW]
    if len(recent) >= _LOGIN_LIMIT:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Qua nhieu lan thu. Vui long cho 15 phut.",
        )
    _login_attempts[ip] = attempts


# ======================================================= AUTH ENDPOINTS ======

class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=64)
    password: str = Field(..., min_length=1, max_length=128)


@admin_router.post("/auth/login")
def login(req: LoginRequest, request: Request) -> dict[str, Any]:
    """Dang nhap admin, tra ve JWT token."""
    client_ip = request.client.host if request.client else "unknown"
    _check_rate_limit(client_ip)

    user = get_admin_user(req.username)
    if not user or not verify_password(req.password, user["password_hash"]):
        _login_attempts[client_ip].append(time.time())
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Ten dang nhap hoac mat khau khong dung.",
        )

    update_admin_last_login(req.username)
    token_data = create_admin_token(req.username, user["role"])
    return {
        **token_data,
        "user": {
            "username": user["username"],
            "display_name": user["display_name"],
            "role": user["role"],
        },
    }


@admin_router.get("/auth/me")
def get_me(current: dict = Depends(get_current_admin)) -> dict[str, Any]:
    """Thong tin tai khoan admin dang dang nhap."""
    user = get_admin_user(current["sub"])
    if not user:
        raise HTTPException(status_code=404, detail="Tai khoan khong ton tai.")
    return {
        "username": user["username"],
        "display_name": user["display_name"],
        "role": user["role"],
        "last_login_at": user["last_login_at"],
    }


# ===================================================== CROWD ENDPOINTS =======

@admin_router.get("/crowd/overview")
def crowd_overview(_: dict = Depends(require_admin_token)) -> dict[str, Any]:
    """Tong quan mat do tat ca khu vuc."""
    data = _load_mock_data()
    attractions = {a["service_id"]: a for a in data["attractions"]}
    snapshots = {s["service_id"]: s for s in data["crowd_snapshots"]}
    zones_meta = {z["zone_id"]: z["name"] for z in data["zones"]}

    zones_map: dict[str, list[dict]] = defaultdict(list)
    open_count = maintenance_count = closed_count = unknown_count = 0

    for service_id, attr in attractions.items():
        snap = snapshots.get(service_id, {})
        status_val = snap.get("operating_status", "unknown")

        if status_val == "open":
            open_count += 1
        elif status_val == "maintenance":
            maintenance_count += 1
        elif status_val in {"temporarily_closed", "permanently_closed", "closed"}:
            closed_count += 1
        else:
            unknown_count += 1

        current_people = snap.get("current_people")
        capacity = attr["crowd_reference"]["comfort_capacity_people"]
        data_quality = snap.get("data_quality", "unavailable")
        occupancy_rate = round(current_people / capacity, 3) if current_people is not None and capacity else None
        crowd_level = _compute_crowd_level(occupancy_rate, data_quality)

        zones_map[attr["zone_id"]].append({
            "service_id": service_id,
            "name": attr["name"],
            "category": attr["category"],
            "indoor": attr["indoor"],
            "operating_status": status_val,
            "status_reason": snap.get("status_reason"),
            "current_people": current_people,
            "queue_people": snap.get("queue_people"),
            "capacity": capacity,
            "occupancy_rate": occupancy_rate,
            "crowd_level": crowd_level,
            "wait_minutes": snap.get("wait_minutes"),
            "data_quality": data_quality,
            "observed_at": snap.get("observed_at"),
            "x_m": attr["location"]["x_m"],
            "y_m": attr["location"]["y_m"],
            "lat": attr["location"].get("lat"),
            "lng": attr["location"].get("lng"),
            "zone_id": attr["zone_id"],
        })

    zones = [
        {
            "zone_id": zone_id,
            "zone_name": zones_meta.get(zone_id, zone_id),
            "attractions": pois,
        }
        for zone_id, pois in zones_map.items()
    ]
    zones.sort(key=lambda z: z["zone_id"])

    return {
        "observed_at": data.get("simulation_now"),
        "total_attractions": len(attractions),
        "open_count": open_count,
        "maintenance_count": maintenance_count,
        "closed_count": closed_count,
        "unknown_count": unknown_count,
        "zones": zones,
    }


# =================================================== BOOKING ENDPOINTS =======

@admin_router.get("/bookings/stats")
def booking_stats(_: dict = Depends(require_admin_token)) -> dict[str, Any]:
    """Thong ke tong hop bookings cho Dashboard."""
    return get_admin_booking_stats()


@admin_router.get("/bookings")
def list_bookings(
    admin_status: str | None = Query(None, description="pending | confirmed | rejected | all"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    _: dict = Depends(require_admin_token),
) -> dict[str, Any]:
    """Danh sach tat ca phien dat lich (co phan trang)."""
    return get_all_sessions_summary(
        admin_status_filter=admin_status if admin_status != "all" else None,
        page=page,
        page_size=page_size,
    )


@admin_router.get("/bookings/{session_id}")
def booking_detail(session_id: str, _: dict = Depends(require_admin_token)) -> dict[str, Any]:
    """Chi tiet day du cua 1 phien: session + messages + plans + events."""
    session = get_or_create_session(session_id)
    messages = get_messages(session_id)
    plans = get_all_plans_for_session(session_id)
    events = get_events(session_id)
    return {
        "session": session,
        "messages": messages,
        "plans": plans,
        "events": events,
    }


class ConfirmRequest(BaseModel):
    plan_id: str = Field(..., min_length=1)
    note: str | None = Field(None, max_length=500)


@admin_router.post("/bookings/{session_id}/confirm")
def confirm_booking(
    session_id: str,
    req: ConfirmRequest,
    current: dict = Depends(get_current_admin),
) -> dict[str, Any]:
    """Xac nhan 1 plan trong phien dat lich."""
    ok = admin_confirm_plan(
        session_id=session_id,
        plan_id=req.plan_id,
        note=req.note,
        confirmed_by=current["sub"],
    )
    if not ok:
        raise HTTPException(status_code=404, detail="Khong tim thay plan hoac session.")
    return {
        "success": True,
        "session_id": session_id,
        "plan_id": req.plan_id,
        "confirmed_by": current["sub"],
        "message": "Da xac nhan lich trinh.",
    }


class RejectRequest(BaseModel):
    reason: str = Field(..., min_length=10, max_length=500)


@admin_router.post("/bookings/{session_id}/reject")
def reject_booking(
    session_id: str,
    req: RejectRequest,
    _: dict = Depends(require_admin_token),
) -> dict[str, Any]:
    """Tu choi toan bo phien dat lich."""
    ok = admin_reject_session(session_id, req.reason)
    if not ok:
        raise HTTPException(status_code=404, detail="Khong tim thay session.")
    return {
        "success": True,
        "session_id": session_id,
        "message": "Da tu choi phien dat lich.",
    }


# ====================================================== MAP ENDPOINTS ========

@admin_router.get("/map/graph")
def get_map_graph() -> dict[str, Any]:
    """Tra ve toan bo nodes va edges cua ban do VinWonders."""
    data = _load_mock_data()
    routing = data.get("routing", {})
    nodes = routing.get("nodes", [])
    edges = routing.get("edges", [])

    # Build POI metadata
    poi_meta = {}
    for a in data.get("attractions", []):
        poi_meta[a["service_id"]] = {
            "name": a["name"],
            "zone_id": a["zone_id"],
            "indoor": a["indoor"],
            "category": a["category"],
            "thrill_level": a.get("thrill_level"),
        }

    # Tinh max toa do de frontend scale
    all_x = [n["x_m"] for n in nodes]
    all_y = [n["y_m"] for n in nodes]
    canvas_w = max(all_x) + 160 if all_x else 1280
    canvas_h = max(all_y) + 160 if all_y else 960

    # Danh loai node
    typed_nodes = []
    poi_ids = {a["service_id"] for a in data.get("attractions", [])}
    for n in nodes:
        if n["node_id"] == START_NODE_ID:
            ntype = "hub"
            cat = "hub"
        elif n["node_id"] in poi_ids:
            ntype = "poi"
            cat = poi_meta.get(n["node_id"], {}).get("category", "attraction")
        else:
            ntype = "junction"
            cat = "junction"
        typed_nodes.append({**n, "type": ntype, "category": cat})

    return {
        "map_id": routing.get("map_id"),
        "canvas_width_m": canvas_w,
        "canvas_height_m": canvas_h,
        "nodes": typed_nodes,
        "edges": edges,
        "poi_metadata": poi_meta,
    }


@admin_router.get("/map/path")
def get_map_path(
    from_node: str = Query(...),
    to_node: str = Query(...),
    _: dict = Depends(require_admin_token),
) -> dict[str, Any]:
    """Tinh duong di ngan nhat giua 2 node bang Dijkstra."""
    data = _load_mock_data()
    routing = data["routing"]
    result = _dijkstra(routing["nodes"], routing["edges"], from_node, to_node)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Khong tim duoc duong tu {from_node} den {to_node}.")
    return {"from_node_id": from_node, "to_node_id": to_node, **result}


@admin_router.get("/map/plan/{session_id}/{plan_index}")
def get_plan_path(
    session_id: str,
    plan_index: int,
    _: dict = Depends(require_admin_token),
) -> dict[str, Any]:
    """Lay chuoi node cua 1 plan cu the trong session."""
    data = _load_mock_data()
    routing = data["routing"]

    plans_records = get_all_plans_for_session(session_id)
    if not plans_records:
        raise HTTPException(status_code=404, detail="Khong co plan nao trong session nay.")

    # Gop tat ca plan tu moi turn lai
    all_plans = []
    for rec in plans_records:
        all_plans.extend(rec["plans"])

    if plan_index < 0 or plan_index >= len(all_plans):
        raise HTTPException(status_code=404, detail=f"Plan index {plan_index} vuot qua so plan hien co ({len(all_plans)}).")

    plan = all_plans[plan_index]
    legs = plan.get("legs", [])

    # Lay sequence node tu legs
    if not legs:
        return {"session_id": session_id, "plan_index": plan_index, "path_segments": [], "total_walking_minutes": 0}

    # Tinh tong path: start -> leg1 -> leg2 -> ... -> end
    start_node = plan.get("start_node_id", START_NODE_ID)
    end_node = plan.get("end_node_id", START_NODE_ID)
    service_sequence = [leg.get("service_id") for leg in legs if leg.get("service_id")]

    all_node_sequence = [start_node]
    segments = []
    total_walk = 0

    node_sequence = [start_node] + service_sequence + [end_node]
    for i in range(len(node_sequence) - 1):
        seg = _dijkstra(routing["nodes"], routing["edges"], node_sequence[i], node_sequence[i + 1])
        if seg:
            segments.append({
                "from": node_sequence[i],
                "to": node_sequence[i + 1],
                **seg,
            })
            total_walk += seg["total_walking_minutes"]
            # Them cac node trung gian (tru dau vi da co trong doan truoc)
            for n in seg["path_nodes"][1:]:
                if all_node_sequence[-1] != n:
                    all_node_sequence.append(n)

    return {
        "session_id": session_id,
        "plan_index": plan_index,
        "style": plan.get("style"),
        "style_label": plan.get("style_label"),
        "full_node_sequence": all_node_sequence,
        "path_segments": segments,
        "total_walking_minutes": total_walk,
    }
