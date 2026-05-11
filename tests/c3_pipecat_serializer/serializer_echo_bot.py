#!/usr/bin/env python3
"""
Test C3: Pipecat Serializer — Vonage Voice Echo Bot

Runs a Pipecat WebSocket server with the Vonage Audio Serializer that:
    1. Listens for WebSocket connections from Vonage Voice API
    2. Receives audio frames from Vonage (Voice NCCO connect action)
    3. Echoes audio frames straight back to Vonage
    4. Handles graceful disconnect

Platform: Runs via FastAPI + Pipecat WebSocket transport.
For Voice API integration: Vonage Voice calls are routed to this server via NCCO connect action.
"""

import asyncio
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv


def find_repo_root(start: Path) -> Path:
    current = start.resolve()
    for candidate in (current, *current.parents):
        if (candidate / ".env").exists():
            return candidate
    workspace_root = Path("/workspace")
    if (workspace_root / ".env").exists():
        return workspace_root
    return start.resolve()


REPO_ROOT = find_repo_root(Path(__file__).parent)
load_dotenv(REPO_ROOT / ".env")


async def main() -> None:
    """Main entry point for Pipecat Vonage Echo Bot WebSocket server."""
    
    # ── Environment variables ─────────────────────────────────────
    ws_host = os.getenv("WS_HOST", "0.0.0.0").strip() or "0.0.0.0"
    ws_port = int(os.getenv("WS_PORT", "8000").strip() or "8000")
    enable_pipecat_logger = os.getenv("VONAGE_ENABLE_PIPECAT_LOGGER", "1").strip().lower() in {"1", "true", "yes"}
    
    # ── Imports ───────────────────────────────────────────────────
    try:
        from loguru import logger
        from pipecat.audio.vad.silero import SileroVADAnalyzer
        from pipecat.frames.frames import Frame, AudioRawFrame
        from pipecat.pipeline.pipeline import Pipeline
        from pipecat.pipeline.runner import PipelineRunner
        from pipecat.pipeline.task import PipelineParams, PipelineTask
        from pipecat.serializers.vonage import VonageFrameSerializer
        from pipecat.transports.websocket.server import (
            WebsocketServerTransport,
            WebsocketServerParams,
        )
        from fastapi import FastAPI, WebSocketDisconnect, WebSocket
        import uvicorn
    except ImportError as exc:
        print(f"ERROR: Missing dependency — {exc}")
        print("  Run: pip install -r requirements.txt")
        sys.exit(1)
    
    if enable_pipecat_logger:
        logger.enable("pipecat")
    
    # ── FastAPI + WebSocket setup ─────────────────────────────────
    app = FastAPI()
    
    # Track active connections for monitoring
    active_connections: set[str] = set()
    
    @app.get("/")
    async def health():
        """Health check endpoint."""
        return {"status": "ok", "active_connections": len(active_connections)}
    
    @app.get("/status")
    async def status():
        """Status endpoint."""
        return {
            "service": "vonage-pipecat-echo-bot",
            "status": "running",
            "active_connections": len(active_connections),
            "ws_endpoint": f"ws://{ws_host}:{ws_port}/ws",
        }
    
    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket):
        """
        WebSocket endpoint for Vonage Audio Serializer.
        
        Vonage Voice API sends audio frames here via NCCO connect action.
        Pipeline echoes audio frames straight back.
        """
        connection_id = f"{websocket.client.host}:{websocket.client.port}" if websocket.client else "unknown"
        active_connections.add(connection_id)
        print(f"✓ Vonage connected: {connection_id}")
        
        try:
            await websocket.accept()
            
            # ── Create Pipecat echo pipeline ──────────────────────
            # VonageFrameSerializer handles Vonage audio format conversion
            serializer = VonageFrameSerializer(
                params=VonageFrameSerializer.InputParams(
                    vonage_sample_rate=16000,  # Vonage Voice API uses 16kHz PCM
                )
            )
            
            # WebsocketServerTransport with serializer communicates via WebSocket
            transport = WebsocketServerTransport(
                params=WebsocketServerParams(
                    audio_out_enabled=True,
                    add_wav_header=False,
                    serializer=serializer,
                    websocket=websocket,
                )
            )
            
            # Simple echo pipeline: input → output (frames pass through unchanged)
            pipeline = Pipeline([
                transport.input(),   # Receive audio from Vonage
                transport.output(),  # Send audio back to Vonage
            ])
            
            task = PipelineTask(
                pipeline,
                params=PipelineParams(allow_interruptions=True),
            )
            
            print(f"  Echo pipeline started for {connection_id}")
            print("  Audio from Vonage → echoed back")
            
            # Run the pipeline
            runner = PipelineRunner()
            await runner.run(task)
            
        except WebSocketDisconnect:
            print(f"  Vonage disconnected: {connection_id}")
        except Exception as e:
            print(f"  ERROR in WebSocket handler ({connection_id}): {e}")
            import traceback
            traceback.print_exc()
        finally:
            active_connections.discard(connection_id)
            print(f"✓ Connection closed: {connection_id}")
    
    # ── Start server ──────────────────────────────────────────────
    print(f"Pipecat Vonage Echo Bot WebSocket Server")
    print(f"  Listening on ws://{ws_host}:{ws_port}/ws")
    print(f"  Waiting for Vonage Voice API connections ...")
    print()
    print("To route Vonage calls to this server:")
    print("  1. In Voice Playground, create NCCO with WebSocket connect action:")
    print(f"     wss://your.domain/ws  (replace with public endpoint)")
    print("  2. Call the phone number to start processing")
    print()
    print("Press Ctrl+C to stop server.\n")
    
    config = uvicorn.Config(
        app,
        host=ws_host,
        port=ws_port,
        log_level="info",
    )
    server = uvicorn.Server(config)
    
    try:
        await server.serve()
    except KeyboardInterrupt:
        print("\nStopped by user. Test C3 complete ✓")
        await server.shutdown()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nTest C3 stopped.")
