from fastapi.testclient import TestClient

from agents.a0.admin_server import get_current_admin, require_admin_token
from agents.a0.server import app


def test_admin_read_endpoints_without_live_server() -> None:
    fake_admin = {"sub": "test_admin", "role": "coordinator"}
    app.dependency_overrides[require_admin_token] = lambda: fake_admin
    app.dependency_overrides[get_current_admin] = lambda: fake_admin

    try:
        with TestClient(app) as client:
            crowd_response = client.get("/admin/crowd/overview")
            assert crowd_response.status_code == 200
            crowd = crowd_response.json()
            assert crowd["total_attractions"] > 0
            assert any(
                attraction["crowd_level"] != "unknown"
                for zone in crowd["zones"]
                for attraction in zone["attractions"]
            )

            graph_response = client.get("/admin/map/graph")
            assert graph_response.status_code == 200
            graph = graph_response.json()
            assert graph["nodes"]
            assert graph["edges"]

            hub_id = next(node["node_id"] for node in graph["nodes"] if node["type"] == "hub")
            poi_id = next(node["node_id"] for node in graph["nodes"] if node["type"] == "poi")
            path_response = client.get(
                "/admin/map/path",
                params={"from_node": hub_id, "to_node": poi_id},
            )
            assert path_response.status_code == 200
            assert path_response.json()["path_nodes"]
    finally:
        app.dependency_overrides.clear()
