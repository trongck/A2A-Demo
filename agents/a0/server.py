"""
Agent A0: Orchestrator & Backend Server.
Chạy trên cổng 8000.
Cung cấp API điều phối tác tử A0, quản lý session và tích hợp với Frontend.
Bám sát mục 2, 4, 6 và 7 của V-AI-Implementation-Plan.md.
"""

import json
from pathlib import Path
from typing import Any
import uuid

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import uvicorn

from agents.a0.orchestrator import run_orchestration, run_orchestration_stream

from shared.llm import get_llm_status
from shared.memory.database import (
    get_events,
    get_messages,
    get_or_create_session,
    init_db,
    update_session,
)

DATA_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "V-AI-Mock-Data.json"

from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield

app = FastAPI(
    title="Agent A0 - Orchestrator API",
    description="Tác tử điều phối trung tâm A0 trong hệ thống đa tác tử VinWonders (A0, A1, A2, MCP, A2A)",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    session_id: str
    message: str
    scenario_id: str | None = None
    preset_data: dict[str, Any] | None = None


class NewSessionRequest(BaseModel):
    scenario_id: str = "base"



@app.get("/")
def root() -> dict[str, Any]:
    return {
        "service": "Agent A0 Orchestrator",
        "port": 8000,
        "status": "running",
        "docs_url": "/docs",
    }


@app.get("/health")
def health_check() -> dict[str, Any]:
    return {"status": "ok", "service": "v_ai_a0_orchestrator", "port": 8000, "llm": get_llm_status()}


@app.get("/api/presets")
def get_presets() -> dict[str, Any]:
    if not DATA_PATH.exists():
        return {"demo_requests": [], "test_scenarios": []}
    with open(DATA_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    return {
        "demo_requests": data.get("demo_requests", []),
        "test_scenarios": data.get("test_scenarios", []),
    }


@app.post("/api/session/new")
def create_new_session(req: NewSessionRequest) -> dict[str, Any]:
    new_id = f"session_{uuid.uuid4().hex[:8]}"
    sess = get_or_create_session(new_id, req.scenario_id)
    return sess


@app.get("/api/session/{session_id}")
def get_session_info(session_id: str) -> dict[str, Any]:
    sess = get_or_create_session(session_id)
    messages = get_messages(session_id)
    events = get_events(session_id)
    return {
        "session": sess,
        "messages": messages,
        "events": events,
    }


@app.get("/api/events/{session_id}")
def get_session_events(session_id: str) -> list[dict[str, Any]]:
    return get_events(session_id)


@app.post("/api/chat")
def handle_chat(req: ChatRequest) -> dict[str, Any]:
    res = run_orchestration(
        session_id=req.session_id,
        user_message=req.message,
        scenario_override=req.scenario_id,
        preset_data=req.preset_data,
    )
    # Lấy danh sách sự kiện mới nhất
    events = get_events(req.session_id)
    res["events"] = events
    return res


@app.post("/api/chat/stream")
def handle_chat_stream(req: ChatRequest):
    return StreamingResponse(
        run_orchestration_stream(
            session_id=req.session_id,
            user_message=req.message,
            scenario_override=req.scenario_id,
            preset_data=req.preset_data,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )



if __name__ == "__main__":
    print("Khởi động Agent A0 Orchestrator Server tại http://127.0.0.1:8000...")
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="info")
