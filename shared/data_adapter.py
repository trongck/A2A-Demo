"""Chuẩn hóa Google Places V2 thành contract nội bộ cho A0/A1/A2/MCP."""

from __future__ import annotations

import json
import math
import re
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any


DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "V-AI-Mock-Data-V2.json"
DATA_REVISION = "google_places_v2"
START_NODE_ID = "start_vinwonders"
PARK_RADIUS_KM = 0.75

_DAY_INDEX = {
    "Thứ Hai": 0,
    "Thứ Ba": 1,
    "Thứ Tư": 2,
    "Thứ Năm": 3,
    "Thứ Sáu": 4,
    "Thứ Bảy": 5,
    "Chủ Nhật": 6,
}


def _distance_km(a: dict[str, float], b: dict[str, float]) -> float:
    lat1, lat2 = math.radians(a["lat"]), math.radians(b["lat"])
    dlat = math.radians(b["lat"] - a["lat"])
    dlng = math.radians(b["lng"] - a["lng"])
    value = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlng / 2) ** 2
    return 6371 * 2 * math.atan2(math.sqrt(value), math.sqrt(1 - value))


def _parse_hours(entries: list[dict[str, str]]) -> dict[str, list[list[str]]]:
    weekly: dict[str, list[list[str]]] = {}
    for entry in entries:
        day = _DAY_INDEX.get(entry.get("day", ""))
        if day is None:
            continue
        text = entry.get("hours", "")
        if text == "Mở cửa cả ngày":
            weekly[str(day)] = [["00:00", "23:59"]]
        elif text != "Đóng cửa":
            weekly[str(day)] = [list(match) for match in re.findall(r"(\d{2}:\d{2}) to (\d{2}:\d{2})", text)]
    return weekly


def _category(place: dict[str, Any]) -> str:
    text = " ".join(place.get("categories") or []).lower()
    if any(word in text for word in ("nhà hàng", "quán cà phê", "đồ ăn", "trà", "kem")):
        return "food"
    if any(word in text for word in ("mạo hiểm", "vòng đu quay", "chèo thuyền", "sân chơi", "công viên nước")):
        return "ride"
    if any(word in text for word in ("cửa hàng", "siêu thị")):
        return "shop"
    if any(word in text for word in ("khách sạn", "nghỉ dưỡng")):
        return "hotel"
    if any(word in text for word in ("công viên", "vườn", "thủy cung", "thu hút", "thắng cảnh", "bãi biển")):
        return "attraction"
    return "service"


def _is_indoor(place: dict[str, Any], category: str) -> bool:
    text = " ".join(place.get("categories") or []).lower()
    if any(word in text for word in ("bãi biển", "vườn", "công viên", "golf", "chèo thuyền", "vòng đu quay")):
        return False
    return category in {"food", "shop", "hotel"} or "thủy cung" in text or "rạp" in text


def _visit_duration(category: str) -> int:
    return {"ride": 30, "attraction": 45, "food": 60, "shop": 30, "hotel": 60}.get(category, 30)


@lru_cache(maxsize=1)
def load_raw_places() -> list[dict[str, Any]]:
    if not DATA_PATH.exists():
        raise FileNotFoundError(f"Không tìm thấy file dữ liệu V2 tại {DATA_PATH}")
    with DATA_PATH.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, list):
        raise ValueError("V-AI-Mock-Data-V2.json phải là một mảng Google Places")
    return data


def load_v2_data(scope: str = "vinwonders") -> dict[str, Any]:
    places = load_raw_places()
    park = next((place for place in places if place.get("title") == "VinWonders Nha Trang"), None)
    if not park:
        raise ValueError("Dữ liệu V2 không có địa điểm gốc VinWonders Nha Trang")
    center = park["location"]
    selected = places if scope == "all" else [
        place for place in places if _distance_km(center, place["location"]) <= PARK_RADIUS_KM
    ]

    attractions: list[dict[str, Any]] = []
    snapshots: list[dict[str, Any]] = []
    nodes = [{
        "node_id": START_NODE_ID,
        "name": "Cổng VinWonders",
        "lat": center["lat"],
        "lng": center["lng"],
        "x_m": 0,
        "y_m": 0,
    }]
    observed_times = []

    for place in selected:
        service_id = place["placeId"]
        category = _category(place)
        location = place["location"]
        x_m = round((location["lng"] - center["lng"]) * 111_320 * math.cos(math.radians(center["lat"])))
        y_m = round((location["lat"] - center["lat"]) * 110_540)
        weekly_hours = _parse_hours(place.get("openingHours") or [])
        permanently_closed = bool(place.get("permanentlyClosed"))
        temporarily_closed = bool(place.get("temporarilyClosed"))
        status = "permanently_closed" if permanently_closed else "temporarily_closed" if temporarily_closed else "unknown"
        scraped_at = place.get("scrapedAt")
        if scraped_at:
            observed_times.append(scraped_at)

        attractions.append({
            "data_revision": DATA_REVISION,
            "service_id": service_id,
            "name": place["title"],
            "zone_id": "vinwonders",
            "category": category,
            "category_name": place.get("categoryName"),
            "categories": place.get("categories") or [],
            "description": place.get("description"),
            "address": place.get("address"),
            "indoor": _is_indoor(place, category),
            "location": {
                "node_id": service_id,
                "lat": location["lat"],
                "lng": location["lng"],
                "x_m": x_m,
                "y_m": y_m,
            },
            "schedule": {
                "mode": "walk_in",
                "weekly_intervals": weekly_hours,
                "raw_opening_hours": place.get("openingHours") or [],
                "visit_duration_minutes": _visit_duration(category),
            },
            "eligibility": {
                "min_age_years": None,
                "min_height_cm": None,
                "max_height_cm": None,
                "adult_required_under_age_years": None,
                "data_quality": "unavailable",
            },
            "crowd_reference": {
                "area_m2": None,
                "comfort_capacity_people": None,
                "data_quality": "unavailable",
            },
            "thrill_level": "none",
            "pricing": {
                "currency": None,
                "price_per_person_vnd": None,
                "raw_price": place.get("price"),
                "data_quality": "unavailable",
            },
            "rating": place.get("totalScore"),
            "reviews_count": place.get("reviewsCount"),
            "rank": place.get("rank"),
            "source": {
                "place_id": service_id,
                "url": place.get("url"),
                "search_string": place.get("searchString"),
                "scraped_at": scraped_at,
            },
        })
        snapshots.append({
            "data_revision": DATA_REVISION,
            "snapshot_id": f"snapshot_{service_id}",
            "service_id": service_id,
            "operating_status": status,
            "status_reason": "Google Places đánh dấu đóng cửa" if status != "unknown" else None,
            "observed_at": scraped_at,
            "source": "google_places_v2",
            "data_quality": "unavailable",
            "current_people": None,
            "queue_people": None,
            "wait_minutes": None,
            "wait_basis": "not_provided",
        })
        nodes.append({
            "node_id": service_id,
            "name": place["title"],
            "lat": location["lat"],
            "lng": location["lng"],
            "x_m": x_m,
            "y_m": y_m,
        })

    min_x = min(node["x_m"] for node in nodes)
    min_y = min(node["y_m"] for node in nodes)
    if min_x < 0 or min_y < 0:
        shift_x, shift_y = max(0, -min_x), max(0, -min_y)
        for node in nodes:
            node["x_m"] += shift_x
            node["y_m"] += shift_y
        for attraction in attractions:
            attraction["location"]["x_m"] += shift_x
            attraction["location"]["y_m"] += shift_y

    edge_pairs: dict[tuple[str, str], tuple[dict[str, Any], dict[str, Any], int]] = {}
    for left in nodes:
        nearest = sorted(
            ((round(_distance_km(left, right) * 1000), right) for right in nodes if right is not left),
            key=lambda item: item[0],
        )[:4]
        for distance_m, right in nearest:
            pair = tuple(sorted((left["node_id"], right["node_id"])))
            edge_pairs[pair] = (left, right, distance_m)

    edges = [{
        "edge_id": f"edge_{index}",
        "from_node_id": left["node_id"],
        "to_node_id": right["node_id"],
        "distance_m": distance_m,
        "walking_minutes": max(1, math.ceil(distance_m / 75)),
        "bidirectional": True,
        "is_open": True,
        "source": "nearest_neighbor_estimate",
    } for index, (left, right, distance_m) in enumerate(edge_pairs.values())]

    simulation_now = max(observed_times) if observed_times else datetime.now().astimezone().isoformat()
    return {
        "schema_version": "2.0",
        "data_revision": DATA_REVISION,
        "data_mode": "google_places",
        "timezone": "Asia/Ho_Chi_Minh",
        "simulation_now": simulation_now,
        "config": {
            "freshness_seconds": 900,
            "crowd_thresholds": {"low_lt": 0.4, "medium_lt": 0.7, "high_lt": 1.0},
        },
        "attractions": attractions,
        "crowd_snapshots": snapshots,
        "park": {"park_id": park["placeId"], "name": park["title"], "center": center},
        "zones": [{"zone_id": "vinwonders", "name": "VinWonders Nha Trang"}],
        "routing": {"source": "coordinates_v2", "map_id": "vinwonders_places_v2", "nodes": nodes, "edges": edges},
        "environment": {"source": "not_provided", "forecast_issued_at": None, "weather_windows": []},
        "demo_requests": [],
        "test_scenarios": [],
    }
