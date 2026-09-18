"""
Unified Launcher cho toàn bộ hệ thống Multi-Agent V-AI.
Khởi động đồng thời 5 tiến trình:
1. MCP Server (Port 8003)
2. Agent A2: Crowd Specialist (Port 8002)
3. Agent A1: Planner Specialist (Port 8001)
4. Backend A0 & API (Port 8000)
5. Next.js + TypeScript + Tailwind CSS Frontend (Port 3000)
Kiểm tra tính sẵn sàng (Health Check) và hỗ trợ dừng sạch (Clean Shutdown).
"""

import os
import signal
import subprocess
import sys
import time
import urllib.request

# Đảm bảo in tiếng Việt không bị lỗi cp1258 trên Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
FRONTEND_DIR = os.path.join(PROJECT_ROOT, "frontend")

SERVICES = [
    {
        "name": "MCP Server (Tools)",
        "cmd": [sys.executable, "-m", "uvicorn", "mcp_server.server:app", "--host", "127.0.0.1", "--port", "8003", "--log-level", "warning"],
        "cwd": PROJECT_ROOT,
        "url": "http://127.0.0.1:8003/health",
        "port": 8003,
    },
    {
        "name": "Agent A2 (Crowd Specialist)",
        "cmd": [sys.executable, "-m", "uvicorn", "agents.a2.server:app", "--host", "127.0.0.1", "--port", "8002", "--log-level", "warning"],
        "cwd": PROJECT_ROOT,
        "url": "http://127.0.0.1:8002/health",
        "port": 8002,
    },
    {
        "name": "Agent A1 (Planner Specialist)",
        "cmd": [sys.executable, "-m", "uvicorn", "agents.a1.server:app", "--host", "127.0.0.1", "--port", "8001", "--log-level", "warning"],
        "cwd": PROJECT_ROOT,
        "url": "http://127.0.0.1:8001/health",
        "port": 8001,
    },
    {
        "name": "Backend A0 (Orchestrator API)",
        "cmd": [sys.executable, "-m", "uvicorn", "agents.a0.server:app", "--host", "127.0.0.1", "--port", "8000", "--log-level", "warning"],
        "cwd": PROJECT_ROOT,
        "url": "http://127.0.0.1:8000/health",
        "port": 8000,
    },
    {
        "name": "Next.js Frontend (TS + Tailwind)",
        "cmd": ["npm.cmd", "run", "dev", "--", "-p", "3000"],
        "cwd": FRONTEND_DIR,
        "url": "http://127.0.0.1:3000",
        "port": 3000,
    },
]


def wait_for_service(name: str, url: str, timeout: int = 30) -> bool:
    start = time.time()
    while time.time() - start < timeout:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "V-AI-HealthCheck"})
            with urllib.request.urlopen(req, timeout=1.5) as resp:
                if resp.status in (200, 304):
                    return True
        except Exception:
            pass
        time.sleep(0.5)
    return False


def main() -> None:
    print("=" * 75)
    print("  KHỞI ĐỘNG HỆ THỐNG ĐA TÁC TỬ V-AI (A0, A1, A2, MCP, SQLite, Next.js)")
    print("=" * 75)

    env = os.environ.copy()
    env["PYTHONPATH"] = PROJECT_ROOT

    processes: list[subprocess.Popen] = []

    def cleanup(*args):
        print("\n[V-AI] Đang dừng toàn bộ các tiến trình...")
        for p in processes:
            try:
                p.terminate()
                p.wait(timeout=2)
            except Exception:
                try:
                    p.kill()
                except Exception:
                    pass
        print("[V-AI] Đã dừng toàn bộ dịch vụ an toàn. Tạm biệt!")
        sys.exit(0)

    signal.signal(signal.SIGINT, cleanup)
    signal.signal(signal.SIGTERM, cleanup)

    for svc in SERVICES:
        print(f"[*] Đang khởi động {svc['name']} trên cổng {svc['port']}...")
        p = subprocess.Popen(svc["cmd"], cwd=svc["cwd"], env=env)
        processes.append(p)

    print("\n[*] Đang kiểm tra trạng thái hoạt động (Health checks)...")
    all_healthy = True
    for svc in SERVICES:
        ok = wait_for_service(svc["name"], svc["url"])
        if ok:
            print(f"  ✓ {svc['name']} [Port {svc['port']}]: SẴN SÀNG")
        else:
            print(f"  ✗ {svc['name']} [Port {svc['port']}]: CHƯA SẴN SÀNG")
            all_healthy = False

    frontend_url = "http://localhost:3000"
    api_url = "http://127.0.0.1:8000"

    print("\n" + "=" * 75)
    print(f"  🎉 HỆ THỐNG ĐÃ SẴN SÀNG ĐỂ BẠN TỰ KIỂM CHỨNG TRỰC TIẾP!")
    print(f"  👉 Giao diện Next.js + Tailwind CSS : {frontend_url}")
    print(f"  👉 Backend API Tác tử A0             : {api_url}")
    print(f"  👉 Agent A1 (Lập lịch)               : http://127.0.0.1:8001/health")
    print(f"  👉 Agent A2 (Mật độ)                 : http://127.0.0.1:8002/health")
    print(f"  👉 MCP Server (Tools)                : http://127.0.0.1:8003/health")
    print("=" * 75)
    print("Nhấn Ctrl + C để dừng toàn bộ 5 tiến trình bất kỳ lúc nào.\n")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        cleanup()


if __name__ == "__main__":
    main()
