#!/usr/bin/env python3
"""
main.py — FastAPI application entry point

Exposes:
  GET  /           — Health check
  GET  /status     — Agent status
  POST /join       — Join a Vonage voice call
  POST /leave      — Leave the current call
  WS   /ws         — Real-time event stream (JSON)

Usage:
  uv run uvicorn main:app --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import structlog
import uvicorn
from dotenv import load_dotenv
from fastapi import Body, FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse

from agent import VonageSerializerVoiceAgent

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

logger = structlog.get_logger(__name__)

# Global agent instance (one call at a time for simplicity)
_agent: VonageSerializerVoiceAgent | None = None
_ws_clients: list[WebSocket] = []


# ── Lifespan ──────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    global _agent
    call_id = os.getenv("VONAGE_CALL_ID", "").strip()
    if call_id:
        logger.info("Auto-joining call on startup", call_id=call_id)
        _agent = VonageSerializerVoiceAgent(on_event=_broadcast)
        _agent.call_id = call_id
        asyncio.create_task(_agent.start())
    yield
    if _agent:
        await _agent.stop()


# ── App ───────────────────────────────────────────────────────────

app = FastAPI(
    title="Vonage Pipecat Serializer Voice AgentCore",
    description="Real-time AI voice agent using serializer flow",
    version="0.1.0",
    lifespan=lifespan,
)


# ── Routes ────────────────────────────────────────────────────────

@app.get("/", response_class=JSONResponse)
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/status", response_class=JSONResponse)
async def status() -> dict[str, Any]:
    if _agent is None:
        return {
            "running": False,
            "call_id": None,
            "connected": False,
            "last_error": None,
            "event_counts": {},
        }
    return {
        "running": _agent._task is not None and not _agent._task.done(),
        "call_id": _agent.call_id,
        "connected": _agent.connected,
        "last_error": _agent.last_error,
        "event_counts": _agent.event_counts,
    }


@app.post("/join", response_class=JSONResponse)
async def join(payload: dict[str, Any] | None = Body(default=None), call_id: str | None = None) -> dict[str, str]:
    global _agent
    payload_call = ""
    if payload:
        payload_call = str(payload.get("call_id", payload.get("session_id", ""))).strip()

    target_call = (payload_call or call_id or os.getenv("VONAGE_CALL_ID", "")).strip()
    if not target_call:
        return JSONResponse(
            status_code=400,
            content={"error": "call_id is required (or set VONAGE_CALL_ID in .env)"},
        )
    if _agent and _agent._task and not _agent._task.done():
        return JSONResponse(
            status_code=409,
            content={"error": "Agent is already running. Call /leave first."},
        )
    _agent = VonageSerializerVoiceAgent(on_event=_broadcast)
    _agent.call_id = target_call
    asyncio.create_task(_agent.start())
    await _broadcast({"event": "agent_joined", "call_id": target_call})
    logger.info("Agent joining call", call_id=target_call)
    return {"status": "joining", "call_id": target_call}


@app.post("/leave", response_class=JSONResponse)
async def leave() -> dict[str, str]:
    global _agent
    if _agent is None:
        return JSONResponse(status_code=404, content={"error": "No active call"})
    call_id = _agent.call_id
    await _agent.stop()
    _agent = None
    await _broadcast({"event": "agent_left", "call_id": call_id})
    return {"status": "left", "call_id": call_id}


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket) -> None:
    await ws.accept()
    _ws_clients.append(ws)
    logger.info("WebSocket client connected")
    try:
        while True:
            # Keep connection alive; server pushes events via _broadcast()
            await asyncio.sleep(30)
            await ws.send_json({"event": "ping"})
    except WebSocketDisconnect:
        pass
    finally:
        _ws_clients.remove(ws)
        logger.info("WebSocket client disconnected")


# ── Helpers ───────────────────────────────────────────────────────

async def _broadcast(payload: dict[str, Any]) -> None:
    """Send a JSON event to all connected WebSocket clients."""
    for ws in list(_ws_clients):
        try:
            await ws.send_json(payload)
        except Exception:
            pass


# ── Entry point ───────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
