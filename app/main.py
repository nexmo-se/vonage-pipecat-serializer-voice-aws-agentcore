#!/usr/bin/env python3
"""
main.py — FastAPI application entry point

Vonage Voice API webhook server + Pipecat pipeline host.

Exposes:
  GET  /           — Health check
  GET  /status     — Agent status
  GET  /answer     — Vonage webhook: returns NCCO routing call to WS /ws
  WS   /ws         — Vonage audio WebSocket (one connection per inbound call)
  POST /hangup     — Cancel the active call pipeline
  WS   /events     — Real-time event stream for monitoring (JSON)
  GET  /metrics    — Prometheus metrics export

Usage:
  uvicorn main:app --host 0.0.0.0 --port 8000

Vonage setup:
  Set your Vonage application's Answer URL to: https://<host>/answer
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
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, Response
from prometheus_client import generate_latest, REGISTRY

from agent import VonageSerializerVoiceAgent
from observability import init_observability

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

logger = structlog.get_logger(__name__)

# Initialize observability (OpenTelemetry + Prometheus)
init_observability()

# Active agent instance (one call at a time)
_agent: VonageSerializerVoiceAgent | None = None
_event_clients: list[WebSocket] = []


# ── Lifespan ──────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Vonage Voice Agent starting up")
    yield
    logger.info("Vonage Voice Agent shutting down")
    if _agent:
        await _agent.cancel()


# ── App ───────────────────────────────────────────────────────────

app = FastAPI(
    title="Vonage Pipecat Serializer Voice AgentCore",
    description="Real-time AI voice agent using Vonage Voice API + AWS Bedrock Nova Sonic + AgentCore",
    version="0.1.0",
    lifespan=lifespan,
)


# ── Routes ────────────────────────────────────────────────────────

@app.get("/metrics", response_class=Response)
async def metrics() -> Response:
    """Prometheus metrics export — for monitoring and observability."""
    return Response(generate_latest(REGISTRY), media_type="text/plain; version=0.0.4")


@app.get("/", response_class=JSONResponse)
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/status", response_class=JSONResponse)
async def status() -> dict[str, Any]:
    if _agent is None:
        return {"running": False, "connected": False, "last_error": None, "event_counts": {}}
    return {
        "running": True,
        "connected": _agent.connected,
        "last_error": _agent.last_error,
        "event_counts": _agent.event_counts,
    }


@app.get("/answer", response_class=JSONResponse)
async def answer(request: Request):
    """Vonage Voice API webhook — returns NCCO directing Vonage to connect to this agent's WebSocket."""
    host = request.headers.get("x-forwarded-host") or request.headers.get(
        "host", f"localhost:{os.getenv('PORT', '8000')}"
    )
    forwarded_proto = request.headers.get("x-forwarded-proto", "").split(",")[0].strip().lower()

    # When behind ngrok/reverse-proxies, request.url.scheme can appear as "http"
    # inside the container even though the public endpoint is HTTPS.
    if forwarded_proto in {"https", "wss"}:
        scheme = "wss"
    elif host.startswith("localhost") or host.startswith("127.0.0.1"):
        scheme = "ws"
    else:
        # Safe default for public hostnames used by Vonage webhooks.
        scheme = "wss"

    ws_url = f"{scheme}://{host}/ws"
    ncco = [
        {
            "action": "connect",
            "endpoint": [
                {
                    "type": "websocket",
                    "uri": ws_url,
                    "content-type": "audio/l16;rate=16000",
                }
            ],
        }
    ]
    logger.info("Vonage answer webhook", ws_url=ws_url)
    return JSONResponse(ncco)


@app.websocket("/ws")
async def vonage_websocket(websocket: WebSocket) -> None:
    """Vonage audio WebSocket — one connection per inbound call."""
    global _agent
    agent = VonageSerializerVoiceAgent(on_event=_broadcast_event)
    _agent = agent
    try:
        await agent.handle_call(websocket)
    except Exception as exc:
        logger.error("Vonage WebSocket handler error", error=str(exc))
    finally:
        if _agent is agent:
            _agent = None


@app.post("/hangup", response_class=JSONResponse)
async def hangup() -> dict[str, str]:
    """Cancel the active call pipeline."""
    if _agent is None:
        return JSONResponse(status_code=404, content={"error": "No active call"})
    await _agent.cancel()
    return {"status": "cancelled"}


@app.websocket("/events")
async def events_websocket(ws: WebSocket) -> None:
    """Real-time event stream for monitoring — NOT the Vonage audio connection."""
    await ws.accept()
    _event_clients.append(ws)
    logger.info("Event stream client connected")
    try:
        while True:
            await asyncio.sleep(30)
            await ws.send_json({"event": "ping"})
    except WebSocketDisconnect:
        pass
    finally:
        if ws in _event_clients:
            _event_clients.remove(ws)
        logger.info("Event stream client disconnected")


# ── Helpers ───────────────────────────────────────────────────────

async def _broadcast_event(payload: dict[str, Any]) -> None:
    """Send a JSON event to all connected /events WebSocket clients."""
    for ws in list(_event_clients):
        try:
            await ws.send_json(payload)
        except Exception:
            pass


# ── Entry point ───────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
