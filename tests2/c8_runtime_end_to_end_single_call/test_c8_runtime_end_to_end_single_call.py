#!/usr/bin/env python3
"""c8: End-to-end single-call validation against deployed runtime/agent.py.

Simulates what Vonage telephony does:
  1. Connects to AgentCore Runtime via presigned WSS URL
  2. Sends a Vonage JSON "connected" header followed by PCM16 audio
  3. Waits for Nova Sonic to respond with audio (may take 10-30s)
  4. Asserts the pipeline completed without critical errors

Pass criteria:
  - WebSocket connection established
  - At least one outbound binary audio frame received from Nova Sonic
  - No fatal errors in the runtime pipeline

Note: Lambda deployment is blocked by account SCPs; this test generates
the presigned URL directly, skipping the Lambda /answer step.
"""

from __future__ import annotations

import asyncio
import json
import math
import os
import struct
import uuid

RUNTIME_ARN = "arn:aws:bedrock-agentcore:us-east-1:589536902306:runtime/vonage_runtime_agent-GC5gEQBPPz"
AWS_REGION = "us-east-1"

# Audio parameters (Vonage 16kHz PCM16 mono)
SAMPLE_RATE = 16000
FRAME_MS = 20
FRAME_SAMPLES = SAMPLE_RATE * FRAME_MS // 1000  # 320 samples = 640 bytes
FRAME_BYTES = FRAME_SAMPLES * 2  # 16-bit = 2 bytes/sample

# Test parameters
SEND_SECONDS = 3          # seconds of audio to send (speech-like to trigger VAD)
WAIT_FOR_RESPONSE_SECONDS = 45  # wait up to 45s for Nova Sonic to respond
CONNECT_TIMEOUT = 20.0
STARTUP_DELAY_SECONDS = 15  # wait for runtime pipeline to initialize before sending audio


def _make_tone_frame(frequency: float = 440.0, frame_index: int = 0) -> bytes:
    """Generate a 20ms sine wave frame (triggers VAD as speech-like content)."""
    samples = []
    offset = frame_index * FRAME_SAMPLES
    for i in range(FRAME_SAMPLES):
        t = (offset + i) / SAMPLE_RATE
        value = int(16000 * math.sin(2 * math.pi * frequency * t))
        value = max(-32768, min(32767, value))
        samples.append(struct.pack("<h", value))
    return b"".join(samples)


def _build_presigned_url() -> str:
    from bedrock_agentcore.runtime import AgentCoreRuntimeClient
    session_id = str(uuid.uuid4())
    client = AgentCoreRuntimeClient(region=AWS_REGION)
    return client.generate_presigned_url(RUNTIME_ARN, session_id=session_id)


async def _run_probe(ws_url: str) -> dict:
    import websockets

    report = {
        "connected": False,
        "json_header_sent": False,
        "audio_frames_sent": 0,
        "outbound_binary_bytes": 0,
        "outbound_text_messages": 0,
        "errors": [],
    }

    try:
        async with websockets.connect(
            ws_url,
            open_timeout=CONNECT_TIMEOUT,
            ping_interval=None,
            max_size=None,
        ) as ws:
            report["connected"] = True

            # Wait for the runtime pipeline to initialize (Silero VAD model download,
            # Bedrock model validation, Nova Sonic setup). During this window the
            # WebSocket is accepted but the transport hasn't started reading yet;
            # sending audio before it's ready triggers AgentCore's write-buffer 1008.
            await asyncio.sleep(STARTUP_DELAY_SECONDS)

            # Step 1: Send Vonage "websocket:connected" header (text JSON frame).
            # VonageFrameSerializer handles or ignores text control frames; not strictly
            # required but mirrors real Vonage behaviour.
            connect_header = json.dumps({
                "event": "websocket:connected",
                "content-type": "audio/l16;rate=16000",
                "original_call_id": str(uuid.uuid4()),
            })
            await ws.send(connect_header)
            report["json_header_sent"] = True

            # Step 2: Send speech-like tone frames to trigger Silero VAD
            send_frames = (SEND_SECONDS * 1000) // FRAME_MS
            for i in range(int(send_frames)):
                frame = _make_tone_frame(440.0, i)
                await ws.send(frame)
                report["audio_frames_sent"] += 1
                await asyncio.sleep(FRAME_MS / 1000)

            # Step 3: Wait for outbound audio from Nova Sonic
            loop = asyncio.get_running_loop()
            end_at = loop.time() + WAIT_FOR_RESPONSE_SECONDS
            while loop.time() < end_at:
                remaining = end_at - loop.time()
                if remaining <= 0:
                    break
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=min(2.0, remaining))
                except asyncio.TimeoutError:
                    continue

                if isinstance(msg, (bytes, bytearray)):
                    report["outbound_binary_bytes"] += len(msg)
                elif isinstance(msg, str):
                    report["outbound_text_messages"] += 1

                # Once we have at least one audio frame back, we can stop
                if report["outbound_binary_bytes"] > 0:
                    break

    except Exception as exc:
        report["errors"].append(str(exc))

    return report


def main() -> int:
    os.environ["AWS_REGION"] = AWS_REGION
    os.environ["AWS_DEFAULT_REGION"] = AWS_REGION

    results: dict = {"stage": "c8_runtime_end_to_end_single_call", "checks": {}}
    passed = 0
    failed = 0

    # Generate presigned URL
    try:
        ws_url = _build_presigned_url()
        results["ws_url_prefix"] = ws_url[:80] + "..."
    except Exception as exc:
        results["status"] = "FAIL"
        results["error"] = f"presigned_url_error: {exc}"
        print(json.dumps(results, indent=2))
        return 1

    # Run probe
    try:
        report = asyncio.run(_run_probe(ws_url))
    except Exception as exc:
        results["status"] = "FAIL"
        results["error"] = f"probe_error: {exc}"
        print(json.dumps(results, indent=2))
        return 1

    results["probe"] = report

    # Check: connected
    if report["connected"]:
        results["checks"]["websocket_connected"] = "PASS"
        passed += 1
    else:
        results["checks"]["websocket_connected"] = f"FAIL: {report.get('errors')}"
        failed += 1

    # Check: audio sent
    if report["audio_frames_sent"] > 0:
        results["checks"]["audio_frames_sent"] = f"PASS ({report['audio_frames_sent']} frames)"
        passed += 1
    else:
        results["checks"]["audio_frames_sent"] = "FAIL: no frames sent"
        failed += 1

    # Check: received audio from Nova Sonic
    if report["outbound_binary_bytes"] > 0:
        results["checks"]["nova_sonic_audio_received"] = (
            f"PASS ({report['outbound_binary_bytes']} bytes)"
        )
        passed += 1
    else:
        results["checks"]["nova_sonic_audio_received"] = (
            "FAIL: no audio received from Nova Sonic within "
            f"{WAIT_FOR_RESPONSE_SECONDS}s"
        )
        failed += 1

    # Check: no fatal errors
    if not report["errors"]:
        results["checks"]["no_fatal_errors"] = "PASS"
        passed += 1
    else:
        results["checks"]["no_fatal_errors"] = f"FAIL: {report['errors']}"
        failed += 1

    results["summary"] = {"passed": passed, "failed": failed}
    results["status"] = "PASS" if failed == 0 else "FAIL"

    print(json.dumps(results, indent=2))
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
