"""
Agent A0: Orchestrator & Backend Server.
Chạy trên cổng 8000.
Cung cấp API điều phối tác tử A0, quản lý session và tích hợp với Frontend.
Bám sát mục 2, 4, 6 và 7 của V-AI-Implementation-Plan.md.
"""

import os
import secrets
import time
from typing import Any
import httpx

from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator
import uvicorn

from shared.security import (
    ALLOWED_ORIGINS,
    SecurityHeadersMiddleware,
    RateLimitMiddleware,
    require_api_key,
    get_logger,
    validate_message,
    validate_session_id,
    MAX_MESSAGE_LENGTH,
)
from shared.security.config import V_AI_INTERNAL_SECRET, INTERNAL_AUTH_ENABLED

from agents.a0.orchestrator import run_orchestration, run_orchestration_stream
from agents.a0.admin_server import admin_router

from shared.memory.database import (
    get_events,
    get_messages,
    get_or_create_session,
    init_db,
    record_event,
    update_session,
)
from shared.data_adapter import DATA_REVISION, load_v2_data

logger = get_logger("a0.server")

from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield

app = FastAPI(
    title="Agent A0 - Orchestrator API",
    description="Tac tu dieu phoi trung tam A0 trong he thong da tac tu VinWonders (A0, A1, A2, MCP, A2A)",
    version="1.0.0",
    lifespan=lifespan,
)

# Mount Admin Portal router
app.include_router(admin_router)

# Security Middlewares (L2, H2)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,  # C2: Whitelist thay vì "*"
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-Api-Key"],
)


class ChatRequest(BaseModel):
    session_id: str = Field(..., max_length=128)
    message: str = Field(..., max_length=MAX_MESSAGE_LENGTH)
    scenario_id: str | None = Field(None, max_length=50)
    preset_data: dict[str, Any] | None = None

    @field_validator("session_id")
    @classmethod
    def session_id_valid(cls, v: str) -> str:
        if not validate_session_id(v):
            raise ValueError("Session ID không hợp lệ.")
        return v

    @field_validator("message")
    @classmethod
    def message_not_empty(cls, v: str) -> str:
        is_valid, err = validate_message(v)
        if not is_valid:
            raise ValueError(err)
        return v.strip()


class NewSessionRequest(BaseModel):
    scenario_id: str = Field("base", max_length=50)



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
    return {"status": "ok", "service": "v_ai", "port": 8000, "data_revision": DATA_REVISION}


@app.get("/api/presets")
def get_presets() -> dict[str, Any]:
    data = load_v2_data()
    return {
        "demo_requests": data.get("demo_requests", []),
        "test_scenarios": data.get("test_scenarios", []),
    }


@app.post("/api/session/new", dependencies=[Depends(require_api_key)])
def create_new_session(req: NewSessionRequest) -> dict[str, Any]:
    # M2: Dùng secrets.token_urlsafe(24) thay vì uuid hex[:8] để tăng entropy
    new_id = f"session_{secrets.token_urlsafe(24)}"
    logger.info("New session created: %s", new_id)
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


@app.post("/api/chat", dependencies=[Depends(require_api_key)])
def handle_chat(req: ChatRequest) -> dict[str, Any]:
    try:
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
    except Exception as e:
        # M6: Không lộ thông tin kỹ thuật nội bộ cho client
        logger.exception("Chat handler error for session %s", req.session_id)
        raise HTTPException(status_code=500, detail="Hệ thống đang gặp sự cố. Vui lòng thử lại.")


@app.post("/api/chat/stream", dependencies=[Depends(require_api_key)])
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

