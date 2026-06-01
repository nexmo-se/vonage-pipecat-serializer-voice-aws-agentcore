#!/usr/bin/env python3
"""Application agent runtime using Vonage Voice API WebSocket + AWS Bedrock Nova Sonic.

This module implements a speech-to-speech AI voice agent that accepts inbound Vonage Voice
API WebSocket connections and routes audio through a Pipecat pipeline powered by AWS Bedrock
Nova Sonic.

Architecture:
  Vonage Voice Call → GET /answer → NCCO → Vonage connects to WS /ws
  WS /ws → FastAPIWebsocketTransport + VonageFrameSerializer → Pipecat Pipeline
         → AWS Bedrock Nova Sonic → Response Audio → Back to Vonage Call

  Optional: AWS Bedrock AgentCore bootstrap to prime the initial context before the
  conversation starts.

Reference:
  - Vonage Pipecat Serializer: https://developer.vonage.com/en/video/guides/vonage-pipecat-serializer-overview
  - Pipecat Framework: https://docs.pipecat.ai/
"""

from __future__ import annotations

import asyncio
import inspect
import json
import os
import time
from pathlib import Path
from typing import Any, Awaitable, Callable

import structlog
from dotenv import load_dotenv

from observability import (
    record_agentcore_latency,
    record_call_duration,
    record_error,
    record_frame_processed,
    record_pipeline_error,
    trace_span,
    validate_agentcore_response,
)

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

logger = structlog.get_logger(__name__)


class VonageSerializerVoiceAgent:
    """Manages the Vonage Voice API + Pipecat voice pipeline for one call.

    One instance is created per inbound Vonage WebSocket connection.
    Call handle_call(websocket) from the FastAPI /ws endpoint to run the pipeline.
    """

    def __init__(
        self,
        *,
        on_event: Callable[[dict[str, Any]], Awaitable[None] | None] | None = None,
    ) -> None:
        self._pipeline_task = None
        self.connected: bool = False
        self.last_error: str | None = None
        self.on_event = on_event
        self.event_counts: dict[str, int] = {"connected": 0, "disconnected": 0, "errors": 0}
        self._call_start_time: float | None = None

    async def _emit(self, event: dict[str, Any]) -> None:
        if self.on_event is None:
            return
        try:
            result = self.on_event(event)
            if inspect.isawaitable(result):
                await result
        except Exception as exc:  # pragma: no cover - best effort callback
            logger.warning("Event callback failed", error=str(exc), event=event.get("event"))

    # ── Public interface ──────────────────────────────────────────

    async def cancel(self) -> None:
        """Cancel the active pipeline (hang up the call)."""
        if self._pipeline_task is not None:
            try:
                cancel_result = self._pipeline_task.cancel()
                if inspect.isawaitable(cancel_result):
                    await cancel_result
            except Exception:
                pass

    async def handle_call(self, websocket) -> None:
        """Accept an inbound Vonage WebSocket and run the full voice pipeline.

        This method blocks until the call ends (Vonage disconnects or pipeline
        is cancelled). Intended to be called directly from the FastAPI /ws endpoint.
        """
        # Record call start time for duration metrics
        self._call_start_time = time.time()
        
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
                logger.warning("Invalid integer env var; using default", name=name, value=value, default=default)
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
            await self._emit({"event": "agent_error", "error": self.last_error})
            return

        # Accept immediately so Vonage doesn't timeout while model/bootstrap init runs.
        await websocket.accept()

        aws_region = os.getenv("AWS_REGION", "us-east-1").strip()
        bedrock_model_id = os.getenv("BEDROCK_MODEL_ID", "amazon.nova-2-sonic-v1:0").strip()
        aws_profile = os.getenv("AWS_PROFILE", os.getenv("AWS_DEFAULT_PROFILE", "")).strip()
        agentcore_runtime_arn = os.getenv("AGENTCORE_AGENT_ARN", "").strip()
        system_instruction = os.getenv(
            "BEDROCK_SYSTEM_INSTRUCTION",
            "You are a helpful voice assistant. Respond warmly and briefly.",
        ).strip()
        agentcore_bootstrap_prompt = os.getenv(
            "AGENTCORE_BOOTSTRAP_PROMPT",
            "Provide one short greeting plus one helpful follow-up question for a live voice assistant session.",
        ).strip()
        bedrock_initial_user_message = os.getenv("BEDROCK_INITIAL_USER_MESSAGE", "").strip()

        bedrock_connect_timeout_seconds = env_int("BEDROCK_CONNECT_TIMEOUT_SECONDS", 10)
        bedrock_read_timeout_seconds = env_int("BEDROCK_READ_TIMEOUT_SECONDS", 60)
        bedrock_max_attempts = env_int("BEDROCK_MAX_ATTEMPTS", 4)
        bedrock_validate_model_id = env_bool("BEDROCK_VALIDATE_MODEL_ID", True)

        session_kwargs: dict[str, Any] = {"region_name": aws_region}
        if aws_profile:
            session_kwargs["profile_name"] = aws_profile
        try:
            aws_session = boto3.Session(**session_kwargs)
            credentials = aws_session.get_credentials()
            if credentials is None:
                raise RuntimeError("boto3 could not resolve AWS credentials")
            frozen_credentials = credentials.get_frozen_credentials()
            aws_client_config = Config(
                retries={"max_attempts": max(1, bedrock_max_attempts), "mode": "standard"},
                connect_timeout=max(1, bedrock_connect_timeout_seconds),
                read_timeout=max(1, bedrock_read_timeout_seconds),
                user_agent_extra="vonage-pipecat-aws-agentcore-app/0.1",
            )
            agentcore_client = (
                aws_session.client("bedrock-agentcore", config=aws_client_config)
                if agentcore_runtime_arn
                else None
            )
        except Exception as exc:
            self.last_error = f"unable to resolve AWS credentials: {exc}"
            logger.error("AWS credential resolution failed", error=str(exc))
            await self._emit({"event": "agent_error", "error": self.last_error})
            return

        if bedrock_validate_model_id:
            try:
                bedrock_client = aws_session.client("bedrock", config=aws_client_config)
                bedrock_client.get_foundation_model(modelIdentifier=bedrock_model_id)
                logger.info("Bedrock model validation passed", model=bedrock_model_id, region=aws_region)
            except ClientError as exc:
                error_code = exc.response.get("Error", {}).get("Code", "Unknown")
                # Fail fast only for clearly invalid model IDs; permission errors remain non-fatal.
                if error_code in {"ValidationException", "ResourceNotFoundException"}:
                    self.last_error = (
                        f"invalid BEDROCK_MODEL_ID '{bedrock_model_id}' for region {aws_region}: {error_code}"
                    )
                    logger.error(
                        "Bedrock model validation failed",
                        model=bedrock_model_id,
                        region=aws_region,
                        code=error_code,
                    )
                    await self._emit({"event": "agent_error", "error": self.last_error})
                    return
                logger.warning(
                    "Bedrock model validation skipped due to API permissions or transient error",
                    model=bedrock_model_id,
                    region=aws_region,
                    code=error_code,
                )

        # Optional serializer-bridge tuning
        monitor_enabled = env_bool("VONAGE_CALL_MONITOR_ENABLED", True)
        monitor_interval_seconds = env_int("VONAGE_CALL_MONITOR_INTERVAL_SECONDS", 15)
        # AWS Nova Sonic docs describe an ~8 minute connection window.
        # Emit an early renewal signal and optionally stop the pipeline at limit.
        nova_session_limit_seconds = env_int("NOVA_SESSION_LIMIT_SECONDS", 470)
        nova_session_warn_seconds = env_int(
            "NOVA_SESSION_WARN_SECONDS",
            max(60, nova_session_limit_seconds - 60),
        )
        nova_stop_on_limit = env_bool("NOVA_SESSION_STOP_ON_LIMIT", False)

        async def invoke_agentcore_bootstrap(prompt: str) -> str | None:
            if not prompt or agentcore_client is None or not agentcore_runtime_arn:
                return None

            def _invoke() -> str | None:
                start_time = time.time()
                response = agentcore_client.invoke_agent_runtime(
                    agentRuntimeArn=agentcore_runtime_arn,
                    contentType="application/json",
                    accept="application/json",
                    payload=json.dumps({"input": prompt}).encode("utf-8"),
                )
                body = response.get("payload") or response.get("response")
                if hasattr(body, "read"):
                    body = body.read()
                if isinstance(body, bytes):
                    body = body.decode("utf-8", errors="replace")
                
                # Record latency
                latency_ms = (time.time() - start_time) * 1000
                record_agentcore_latency(latency_ms)
                
                result = (body or "").strip() or None
                
                # Validate response
                if result:
                    is_valid, error_reason = validate_agentcore_response(result)
                    if not is_valid:
                        logger.warning(
                            "AgentCore response validation failed",
                            reason=error_reason,
                            response_preview=result[:100]
                        )
                        return None
                
                return result

            try:
                return await asyncio.to_thread(_invoke)
            except Exception as exc:
                logger.warning("AgentCore bootstrap invocation failed; continuing without it", error=str(exc))
                record_error("agentcore_bootstrap_failed")
                await self._emit({"event": "agentcore_bootstrap_failed", "error": str(exc)})
                return None

        bootstrap_message = await invoke_agentcore_bootstrap(agentcore_bootstrap_prompt)

        # Workaround for current Nova Sonic adapter behavior:
        # if initial context messages are empty, the adapter can fail while
        # building ConvertedMessages. Seed with system instruction.
        context_messages: list[dict] = [
            {
                "role": "system",
                "content": system_instruction,
            }
        ]
        if bootstrap_message:
            context_messages.append(
                {
                    "role": "user",
                    "content": (
                        "Use the following context to shape your first response: "
                        f"{bootstrap_message}"
                    ),
                }
            )
        if bedrock_initial_user_message:
            context_messages.append(
                {
                    "role": "user",
                    "content": (
                        "When the caller connects, start by saying exactly this greeting: "
                        f"{bedrock_initial_user_message}"
                    ),
                }
            )
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
            await self._emit({"event": "agent_error", "error": self.last_error})
            return

        # Vonage Voice API WebSocket transport — Vonage connects to us on /ws
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
                fixed_audio_packet_size=640,  # 20ms PCM frame at 16kHz
                serializer=serializer,
                vad_analyzer=SileroVADAnalyzer(),
            ),
        )

        # 3-stage speech-to-speech pipeline (no text aggregators)
        pipeline = Pipeline([
            transport.input(),
            nova_sonic,
            transport.output(),
        ])

        self._pipeline_task = PipelineTask(
            pipeline,
            params=PipelineParams(allow_interruptions=True),
        )

        session_started_at: float | None = None
        renewal_emitted = False
        renewal_stop_triggered = False

        async def monitor_loop() -> None:
            nonlocal renewal_emitted, renewal_stop_triggered
            while True:
                await asyncio.sleep(max(1, monitor_interval_seconds))
                session_age_seconds: int | None = None
                if session_started_at is not None:
                    session_age_seconds = int(asyncio.get_running_loop().time() - session_started_at)

                logger.info(
                    "Monitor snapshot",
                    connected=self.connected,
                    event_counts=self.event_counts,
                    session_age_seconds=session_age_seconds,
                )

                if session_age_seconds is None:
                    continue

                if not renewal_emitted and session_age_seconds >= nova_session_warn_seconds:
                    renewal_emitted = True
                    logger.warning(
                        "Nova Sonic session renewal recommended",
                        session_age_seconds=session_age_seconds,
                        warn_after_seconds=nova_session_warn_seconds,
                        limit_seconds=nova_session_limit_seconds,
                    )
                    await self._emit(
                        {
                            "event": "session_renewal_recommended",
                            "session_age_seconds": session_age_seconds,
                            "warn_after_seconds": nova_session_warn_seconds,
                            "limit_seconds": nova_session_limit_seconds,
                            "recommended_action": "Allow Vonage to reconnect after the current call ends",
                        }
                    )
                if (
                    nova_stop_on_limit
                    and not renewal_stop_triggered
                    and session_age_seconds >= nova_session_limit_seconds
                ):
                    renewal_stop_triggered = True
                    self.last_error = "Nova Sonic session duration limit reached; allow Vonage to reconnect"
                    logger.warning(
                        "Stopping pipeline at Nova Sonic session limit",
                        session_age_seconds=session_age_seconds,
                        limit_seconds=nova_session_limit_seconds,
                    )
                    await self._emit(
                        {
                            "event": "session_renewal_required",
                            "session_age_seconds": session_age_seconds,
                            "limit_seconds": nova_session_limit_seconds,
                            "error": self.last_error,
                        }
                    )
                    cancel_result = self._pipeline_task.cancel()
                    if inspect.isawaitable(cancel_result):
                        await cancel_result
                    return

        monitor_task: asyncio.Task | None = None
        if monitor_enabled:
            monitor_task = asyncio.create_task(monitor_loop())

        # Push LLMContextFrame when Vonage WebSocket connects to open the Bedrock stream
        @transport.event_handler("on_client_connected")
        async def on_client_connected(t, client):
            nonlocal session_started_at
            self.connected = True
            session_started_at = asyncio.get_running_loop().time()
            self.event_counts["connected"] += 1
            logger.info("Vonage WebSocket connected", model=bedrock_model_id)
            await self._emit({"event": "call_connected", "model": bedrock_model_id})
            await self._pipeline_task.queue_frame(LLMContextFrame(context))
            # If an initial assistant message is configured, force the first run so callers
            # hear the greeting immediately after connect.
            if bedrock_initial_user_message:
                await self._pipeline_task.queue_frame(LLMRunFrame())
                logger.info("Queued initial assistant greeting")

        @transport.event_handler("on_client_disconnected")
        async def on_client_disconnected(t, client):
            self.connected = False
            self.event_counts["disconnected"] += 1
            logger.info("Vonage WebSocket disconnected")
            await self._emit({"event": "call_disconnected"})

        logger.info(
            "Pipeline starting",
            aws_region=aws_region,
            model=bedrock_model_id,
            aws_profile=aws_profile or None,
            agentcore_bootstrap_enabled=bool(agentcore_runtime_arn),
            agentcore_bootstrap_applied=bool(bootstrap_message),
        )
        await self._emit({
            "event": "agent_starting",
            "model": bedrock_model_id,
            "region": aws_region,
            "agentcore_bootstrap_enabled": bool(agentcore_runtime_arn),
            "agentcore_bootstrap_applied": bool(bootstrap_message),
        })

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
            await self._emit({"event": "agent_error", "error": self.last_error})
        finally:
            # Record call duration metrics
            if self._call_start_time is not None:
                duration_seconds = time.time() - self._call_start_time
                record_call_duration(duration_seconds, status=call_status)
                logger.info(
                    "Call completed",
                    duration_seconds=round(duration_seconds, 1),
                    status=call_status,
                    error=self.last_error,
                )
            
            if monitor_task and not monitor_task.done():
                monitor_task.cancel()
                try:
                    await monitor_task
                except asyncio.CancelledError:
                    pass
            self.connected = False
            logger.info("Pipeline stopped")
            await self._emit({"event": "agent_stopped"})
