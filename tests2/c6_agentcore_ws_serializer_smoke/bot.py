#!/usr/bin/env python3
"""c6 runtime bot: VonageFrameSerializer + FastAPIWebsocketTransport smoke agent.

Deployed to AgentCore Runtime on port 8080. Accepts Vonage-format WebSocket
connections via BedrockAgentCoreApp's /ws route, deserializes binary PCM frames
via VonageFrameSerializer, counts them, and logs the result. No AI services —
validates only the serializer + transport layer inside AgentCore Runtime.

Architecture:
  Vonage client → presigned WSS URL (wss://.../runtimes/{arn}/ws)
  → AgentCore Runtime → BedrockAgentCoreApp /ws
  → FastAPIWebsocketTransport + VonageFrameSerializer → FrameCounterProcessor
"""

from __future__ import annotations

from bedrock_agentcore.runtime import BedrockAgentCoreApp
from loguru import logger
from pipecat.frames.frames import AudioRawFrame, Frame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.serializers.vonage import VonageFrameSerializer
from pipecat.transports.websocket.fastapi import (
    FastAPIWebsocketParams,
    FastAPIWebsocketTransport,
)
from starlette.websockets import WebSocket

app = BedrockAgentCoreApp()


class FrameCounterProcessor(FrameProcessor):
    """Passes all frames through while counting inbound audio frames."""

    def __init__(self):
        super().__init__()
        self.inbound_audio_count = 0

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        if isinstance(frame, AudioRawFrame):
            self.inbound_audio_count += 1
            if self.inbound_audio_count == 1:
                logger.info(
                    "First inbound audio frame received",
                    sample_rate=frame.sample_rate,
                    num_channels=frame.num_channels,
                    bytes=len(frame.audio),
                )
        await self.push_frame(frame, direction)


@app.websocket
async def ws_handler(websocket: WebSocket, context) -> None:
    """Handle WebSocket connections routed by BedrockAgentCoreApp to /ws."""
    logger.info("WebSocket connection received via BedrockAgentCoreApp /ws")
    await websocket.accept()

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
            fixed_audio_packet_size=640,  # 20 ms PCM at 16 kHz
            serializer=serializer,
        ),
    )

    counter = FrameCounterProcessor()

    pipeline = Pipeline([
        transport.input(),
        counter,
        transport.output(),
    ])

    task = PipelineTask(
        pipeline,
        params=PipelineParams(allow_interruptions=True),
    )

    @transport.event_handler("on_client_connected")
    async def on_connected(transport, client):
        logger.info("Client connected — VonageFrameSerializer active")

    @transport.event_handler("on_client_disconnected")
    async def on_disconnected(transport, client):
        logger.info(
            "Client disconnected",
            inbound_audio_frames=counter.inbound_audio_count,
        )
        await task.cancel()

    runner = PipelineRunner(handle_sigint=False)
    await runner.run(task)


if __name__ == "__main__":
    app.run(port=8080)
