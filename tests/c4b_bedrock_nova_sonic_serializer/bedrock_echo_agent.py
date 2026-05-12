#!/usr/bin/env python3
"""
Test C4b: AWS Bedrock Nova Sonic + Vonage Audio Serializer — Live Agent

Runs a Pipecat WebSocket server that:
    1. Listens for WebSocket connections from Vonage Voice API
    2. Receives audio frames from the caller (PCM 16kHz via Vonage Audio Serializer)
    3. Passes audio through AWS Bedrock Nova Sonic (speech-to-speech LLM)
    4. Streams response audio back to the caller via Vonage

This test validates:
    - AWS Bedrock Nova Sonic speech-to-speech integration
    - Vonage Audio Serializer WebSocket transport (VonageFrameSerializer)
    - End-to-end voice pipeline: caller → Nova Sonic → caller

Architecture:
    Vonage Voice API ──WebSocket──▶ AudioSerializer Transport
                                          │
                                    Nova Sonic LLM
                                    (speech-to-speech)
                                          │
    Vonage Voice API ◀─WebSocket── AudioSerializer Transport

Run:
    python bedrock_echo_agent.py
    AWS_PROFILE=vonage-dev python bedrock_echo_agent.py
"""

import asyncio
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

# 20ms @ 16kHz, PCM16 mono => 640 bytes.
VONAGE_AUDIO_PACKET_BYTES = 640


async def run_bedrock_nova_sonic_agent() -> None:
    def env_bool(name: str, default: bool) -> bool:
        value = os.getenv(name)
        if value is None:
            return default
        return value.strip().lower() in {"1", "true", "yes", "on"}

    def env_int(name: str, default: int) -> int:
        value = os.getenv(name, "").strip()
        if not value:
            return default
        try:
            return int(value)
        except ValueError:
            print(f"WARN: Invalid {name}={value!r}, using default {default}")
            return default

    # ── WebSocket server configuration ────────────────────────────
    ws_host = os.getenv("WS_HOST", "0.0.0.0").strip() or "0.0.0.0"
    ws_port = env_int("WS_PORT", 8000)

    # ── AWS Bedrock configuration ─────────────────────────────────
    bedrock_model_id = os.getenv("BEDROCK_MODEL_ID", "amazon.nova-2-sonic-v1:0").strip()
    aws_region = os.getenv("AWS_REGION", "us-east-1").strip()
    aws_profile = os.getenv("AWS_PROFILE", os.getenv("AWS_DEFAULT_PROFILE", "")).strip()

    enable_pipecat_logger = env_bool("VONAGE_ENABLE_PIPECAT_LOGGER", True)

    # ── Imports ───────────────────────────────────────────────────
    try:
        import boto3
        from loguru import logger
        from pipecat.audio.vad.silero import SileroVADAnalyzer
        from pipecat.frames.frames import LLMContextFrame
        from pipecat.pipeline.pipeline import Pipeline
        from pipecat.pipeline.runner import PipelineRunner
        from pipecat.pipeline.task import PipelineParams, PipelineTask
        from pipecat.processors.aggregators.llm_context import LLMContext
        from pipecat.serializers.vonage import VonageFrameSerializer
        from pipecat.services.aws.nova_sonic.llm import AWSNovaSonicLLMService, Params
        from pipecat.transports.websocket.fastapi import (
            FastAPIWebsocketTransport,
            FastAPIWebsocketParams,
        )
        from fastapi import FastAPI, WebSocket, Request
        from fastapi.responses import JSONResponse
        import uvicorn
    except ImportError as exc:
        print(f"ERROR: Missing dependency — {exc}")
        print("  Run: pip install -r requirements.txt")
        sys.exit(1)

    if enable_pipecat_logger:
        logger.enable("pipecat")

    # ── Resolve AWS credentials ───────────────────────────────────
    session_kwargs = {"region_name": aws_region}
    if aws_profile:
        session_kwargs["profile_name"] = aws_profile

    try:
        aws_session = boto3.Session(**session_kwargs)
        credentials = aws_session.get_credentials()
        if credentials is None:
            raise RuntimeError("boto3 could not resolve AWS credentials")
        frozen = credentials.get_frozen_credentials()
    except Exception as exc:
        print(f"ERROR: Unable to resolve AWS credentials — {exc}")
        sys.exit(1)

    print(f"✓ AWS credentials resolved (profile: {aws_profile or 'default chain'}, region: {aws_region})")

    # ── FastAPI + WebSocket server ────────────────────────────────
    app = FastAPI()

    @app.get("/")
    async def health():
        return {"status": "ok", "model": bedrock_model_id}

    @app.get("/answer")
    async def answer(request: Request):
        """Vonage Voice API answer webhook — returns NCCO to connect call to this agent."""
        host = request.headers.get("host", f"localhost:{ws_port}")
        scheme = "wss" if request.url.scheme == "https" else "ws"
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
        print(f"  Answer webhook called → routing call to {ws_url}")
        return JSONResponse(ncco)

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket):
        """Vonage Voice API connects here via NCCO WebSocket connect action."""
        connection_id = f"{websocket.client.host}:{websocket.client.port}" if websocket.client else "unknown"
        print(f"✓ Vonage connected: {connection_id}")

        try:
            await websocket.accept()

            # ── VonageFrameSerializer + WebSocket Transport ───────
            serializer = VonageFrameSerializer(
                params=VonageFrameSerializer.InputParams(
                    vonage_sample_rate=16000,
                )
            )
            transport = FastAPIWebsocketTransport(
                websocket=websocket,
                params=FastAPIWebsocketParams(
                    audio_in_enabled=True,
                    audio_out_enabled=True,
                    add_wav_header=False,
                    fixed_audio_packet_size=VONAGE_AUDIO_PACKET_BYTES,
                    serializer=serializer,
                    vad_analyzer=SileroVADAnalyzer(),
                ),
            )

            # ── Nova Sonic LLM (speech-to-speech) ────────────────
            nova_sonic = AWSNovaSonicLLMService(
                access_key_id=frozen.access_key,
                secret_access_key=frozen.secret_key,
                session_token=frozen.token,
                region=aws_region,
                model=bedrock_model_id,
                params=Params(
                    input_sample_rate=16000,
                    output_sample_rate=16000,
                ),
                system_instruction=(
                    "You are a helpful voice assistant. Respond warmly and briefly."
                ),
            )

            # Workaround: pipecat adapter bug — ConvertedMessages() called with no
            # args when messages list is empty (missing required 'messages' field).
            # Providing the system message ensures the list is non-empty and also
            # correctly seeds the session instruction (context takes priority over
            # the constructor's system_instruction param).
            context = LLMContext(messages=[
                {"role": "system", "content": "You are a helpful voice assistant. Respond warmly and briefly."}
            ])

            # ── Pipeline: audio in → Nova Sonic → audio out ───────
            # Speech-to-speech: audio frames flow directly to Nova Sonic.
            # No text aggregators needed; Nova Sonic manages context internally.
            pipeline = Pipeline([
                transport.input(),
                nova_sonic,
                transport.output(),
            ])

            task = PipelineTask(
                pipeline,
                params=PipelineParams(allow_interruptions=True),
            )

            @transport.event_handler("on_client_connected")
            async def on_connected(t, client):
                print(f"  ✓ Listening for audio (Nova Sonic ready)…")
                # Push initial context to trigger Nova Sonic's Bedrock stream
                # initialization (_finish_connecting_if_context_available).
                await task.queue_frame(LLMContextFrame(context))

            @transport.event_handler("on_client_disconnected")
            async def on_disconnected(t, client):
                print(f"  Vonage disconnected: {connection_id}")
                await task.cancel()

            runner = PipelineRunner(handle_sigint=False)
            await runner.run(task)

        except Exception as exc:
            print(f"ERROR in WebSocket handler: {exc}")
        finally:
            print(f"  Connection closed: {connection_id}")

    print(f"\nBedrock Nova Sonic + Vonage Audio Serializer Agent")
    print(f"  Model:     {bedrock_model_id}")
    print(f"  Region:    {aws_region}")
    print(f"  Listening: ws://0.0.0.0:{ws_port}/ws")
    print(f"\nTo connect a live call:")
    print(f"  1. Run: ngrok http {ws_port}")
    print(f"  2. Set Vonage app Answer URL to: https://<ngrok-host>/answer")
    print(f"  3. Call your Vonage number — Vonage will connect to this agent")
    print(f"\nPress Ctrl+C to stop.\n")

    config = uvicorn.Config(app, host=ws_host, port=ws_port, log_level="warning")
    server = uvicorn.Server(config)
    await server.serve()


if __name__ == "__main__":
    try:
        asyncio.run(run_bedrock_nova_sonic_agent())
    except KeyboardInterrupt:
        print("\nStopped. C4b live agent test complete ✓")
