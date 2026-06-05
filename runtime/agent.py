#!/usr/bin/env python3
"""AgentCore Runtime agent — Vonage Voice API WebSocket + AWS Bedrock Nova Sonic.

Runs inside AWS Bedrock AgentCore Runtime on port 8080.
BedrockAgentCoreApp exposes /ws for WebSocket connections routed from the
AgentCore presigned URL (wss://.../runtimes/{arn}/ws).

Local dev: use app/agent.py + app/main.py with ngrok instead.
"""

from __future__ import annotations

import asyncio
import inspect
import os
import time
from typing import Any

import structlog
from bedrock_agentcore.runtime import BedrockAgentCoreApp
from starlette.websockets import WebSocket

logger = structlog.get_logger(__name__)

app = BedrockAgentCoreApp()


@app.websocket
async def ws_handler(websocket: WebSocket, context) -> None:
    """Handle inbound Vonage WebSocket connection routed via AgentCore /ws."""
    # Must accept before FastAPIWebsocketTransport initialises — BedrockAgentCoreApp
    # does not auto-accept.
    await websocket.accept()

    agent = _VoiceAgent()
    await agent.handle_call(websocket)


class _VoiceAgent:
    """One instance per inbound call. Runs the Vonage + Nova Sonic pipeline."""

    def __init__(self) -> None:
        self._pipeline_task = None
        self.connected: bool = False
        self.last_error: str | None = None
        self._call_start_time: float | None = None

    async def handle_call(self, websocket: WebSocket) -> None:
        self._call_start_time = time.time()

        def env_bool(name: str, default: bool) -> bool:
            v = os.getenv(name)
            return default if v is None else v.strip().lower() in {"1", "true", "yes", "on"}

        def env_int(name: str, default: int) -> int:
            v = os.getenv(name, "").strip()
            if not v:
                return default
            try:
                return int(v)
            except ValueError:
                logger.warning("Invalid integer env var; using default", name=name, default=default)
                return default

        try:
            import boto3
            from botocore.config import Config
            from botocore.exceptions import ClientError
            from pipecat.audio.vad.silero import SileroVADAnalyzer
            from pipecat.frames.frames import LLMContextFrame, LLMRunFrame
            from pipecat.pipeline.pipeline import Pipeline
            from pipecat.pipeline.runner import PipelineRunner
            from pipecat.pipeline.task import PipelineParams, PipelineTask
            from pipecat.processors.aggregators.llm_context import LLMContext
            from pipecat.serializers.vonage import VonageFrameSerializer
            from pipecat.services.aws.nova_sonic.llm import AWSNovaSonicLLMService, Params
            from pipecat.transports.websocket.fastapi import (
                FastAPIWebsocketParams,
                FastAPIWebsocketTransport,
            )
        except ImportError as exc:
            self.last_error = f"missing dependency: {exc}"
            logger.error("Missing dependency", error=str(exc))
            return

        aws_region = os.getenv("AWS_REGION", "us-east-1").strip()
        bedrock_model_id = os.getenv("BEDROCK_MODEL_ID", "amazon.nova-2-sonic-v1:0").strip()
        system_instruction = os.getenv(
            "BEDROCK_SYSTEM_INSTRUCTION",
            "You are a nurse triage voice assistant. Ask one short question at a time. "
            "Capture symptom, onset, severity from 1-10, and red flags. Keep responses "
            "concise and empathetic. If severe red-flag symptoms are mentioned, advise "
            "immediate emergency care and escalate.",
        ).strip()
        bedrock_initial_user_message = os.getenv(
            "BEDROCK_INITIAL_USER_MESSAGE",
            "Hello, I am your nurse intake assistant. I will ask a few brief triage "
            "questions to help route your care quickly. What symptom are you experiencing now?",
        ).strip()

        bedrock_connect_timeout = env_int("BEDROCK_CONNECT_TIMEOUT_SECONDS", 10)
        bedrock_read_timeout = env_int("BEDROCK_READ_TIMEOUT_SECONDS", 60)
        bedrock_max_attempts = env_int("BEDROCK_MAX_ATTEMPTS", 4)
        bedrock_validate_model_id = env_bool("BEDROCK_VALIDATE_MODEL_ID", True)

        # Inside AgentCore Runtime, boto3 picks up credentials from IMDS automatically.
        # No AWS_PROFILE or static keys needed.
        try:
            aws_session = boto3.Session(region_name=aws_region)
            credentials = aws_session.get_credentials()
            if credentials is None:
                raise RuntimeError("boto3 could not resolve AWS credentials from IMDS")
            frozen_credentials = credentials.get_frozen_credentials()
            aws_client_config = Config(
                retries={"max_attempts": max(1, bedrock_max_attempts), "mode": "standard"},
                connect_timeout=max(1, bedrock_connect_timeout),
                read_timeout=max(1, bedrock_read_timeout),
                user_agent_extra="vonage-pipecat-aws-agentcore-runtime/0.1",
            )
        except Exception as exc:
            self.last_error = f"unable to resolve AWS credentials: {exc}"
            logger.error("AWS credential resolution failed", error=str(exc))
            return

        if bedrock_validate_model_id:
            try:
                bedrock_client = aws_session.client("bedrock", config=aws_client_config)
                bedrock_client.get_foundation_model(modelIdentifier=bedrock_model_id)
                logger.info("Bedrock model validation passed", model=bedrock_model_id)
            except ClientError as exc:
                error_code = exc.response.get("Error", {}).get("Code", "Unknown")
                if error_code in {"ValidationException", "ResourceNotFoundException"}:
                    self.last_error = f"invalid BEDROCK_MODEL_ID '{bedrock_model_id}': {error_code}"
                    logger.error("Bedrock model validation failed", model=bedrock_model_id, code=error_code)
                    return
                logger.warning("Bedrock model validation skipped", code=error_code)

        # Build initial context. No AgentCore bootstrap — this agent IS in AgentCore.
        context_messages: list[dict[str, Any]] = [{"role": "system", "content": system_instruction}]
        if bedrock_initial_user_message:
            context_messages.append({
                "role": "user",
                "content": (
                    "When the caller connects, start by saying exactly this greeting: "
                    f"{bedrock_initial_user_message}"
                ),
            })
        context = LLMContext(messages=context_messages)

        try:
            nova_sonic = AWSNovaSonicLLMService(
                access_key_id=frozen_credentials.access_key,
                secret_access_key=frozen_credentials.secret_key,
                session_token=frozen_credentials.token,
                region=aws_region,
                model=bedrock_model_id,
                params=Params(
                    input_sample_rate=16000,
                    input_channel_count=1,
                    output_sample_rate=16000,
                    output_channel_count=1,
                ),
                system_instruction=system_instruction,
            )
        except Exception as exc:
            self.last_error = f"failed to initialize Nova Sonic: {exc}"
            logger.error("Nova Sonic initialization failed", error=str(exc))
            return

        serializer = VonageFrameSerializer(
            params=VonageFrameSerializer.InputParams(vonage_sample_rate=16000)
        )

        transport = FastAPIWebsocketTransport(
            websocket=websocket,
            params=FastAPIWebsocketParams(
                audio_in_enabled=True,
                audio_out_enabled=True,
                add_wav_header=False,
                fixed_audio_packet_size=640,  # 20ms PCM at 16kHz
                serializer=serializer,
                vad_analyzer=SileroVADAnalyzer(),
            ),
        )

        pipeline = Pipeline([
            transport.input(),
            nova_sonic,
            transport.output(),
        ])

        self._pipeline_task = PipelineTask(
            pipeline,
            params=PipelineParams(allow_interruptions=True),
        )

        # Nova Sonic has an ~8 minute session window. Warn before the limit.
        nova_session_limit = env_int("NOVA_SESSION_LIMIT_SECONDS", 470)
        nova_session_warn = env_int("NOVA_SESSION_WARN_SECONDS", max(60, nova_session_limit - 60))
        nova_stop_on_limit = env_bool("NOVA_SESSION_STOP_ON_LIMIT", False)
        monitor_interval = env_int("VONAGE_CALL_MONITOR_INTERVAL_SECONDS", 15)

        session_started_at: float | None = None
        renewal_emitted = False
        renewal_stop_triggered = False

        async def monitor_loop() -> None:
            nonlocal renewal_emitted, renewal_stop_triggered
            while True:
                await asyncio.sleep(max(1, monitor_interval))
                if session_started_at is None:
                    continue
                age = int(asyncio.get_running_loop().time() - session_started_at)
                logger.info("Monitor snapshot", connected=self.connected, session_age_seconds=age)
                if not renewal_emitted and age >= nova_session_warn:
                    renewal_emitted = True
                    logger.warning("Nova Sonic session renewal recommended", session_age_seconds=age)
                if nova_stop_on_limit and not renewal_stop_triggered and age >= nova_session_limit:
                    renewal_stop_triggered = True
                    self.last_error = "Nova Sonic session limit reached"
                    logger.warning("Stopping pipeline at Nova Sonic session limit", session_age_seconds=age)
                    cancel_result = self._pipeline_task.cancel()
                    if inspect.isawaitable(cancel_result):
                        await cancel_result
                    return

        monitor_task: asyncio.Task | None = asyncio.create_task(monitor_loop())

        @transport.event_handler("on_client_connected")
        async def on_client_connected(t, client):
            nonlocal session_started_at
            self.connected = True
            session_started_at = asyncio.get_running_loop().time()
            logger.info("Vonage WebSocket connected", model=bedrock_model_id)
            await self._pipeline_task.queue_frame(LLMContextFrame(context))
            if bedrock_initial_user_message:
                await self._pipeline_task.queue_frame(LLMRunFrame())

        @transport.event_handler("on_client_disconnected")
        async def on_client_disconnected(t, client):
            self.connected = False
            logger.info("Vonage WebSocket disconnected")

        logger.info(
            "Pipeline starting",
            region=aws_region,
            model=bedrock_model_id,
        )

        runner = PipelineRunner()
        call_status = "completed"
        try:
            await runner.run(self._pipeline_task)
        except asyncio.CancelledError:
            call_status = "cancelled"
            raise
        except Exception as exc:
            self.last_error = str(exc)
            call_status = "failed"
            logger.exception("Pipeline execution failed")
        finally:
            if self._call_start_time is not None:
                duration = round(time.time() - self._call_start_time, 1)
                logger.info("Call completed", duration_seconds=duration, status=call_status)
            if monitor_task and not monitor_task.done():
                monitor_task.cancel()
                try:
                    await monitor_task
                except asyncio.CancelledError:
                    pass
            self.connected = False
            logger.info("Pipeline stopped")


if __name__ == "__main__":
    app.run(port=8080)
