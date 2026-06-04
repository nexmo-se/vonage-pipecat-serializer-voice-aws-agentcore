#!/usr/bin/env python3
"""C6 smoke test: AgentCore runtime websocket + serializer path.

This validates the highest-risk unknown before main app changes:
- Connect to AgentCore runtime websocket (presigned URL)
- Send Vonage-like PCM audio frames (16kHz, 16-bit mono, 20ms => 640 bytes)
- Optionally require outbound media from runtime
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import uuid
from pathlib import Path
from typing import Any

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - optional dependency
    def load_dotenv(*_args: Any, **_kwargs: Any) -> bool:
        return False


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="C6 AgentCore websocket serializer smoke test")
    parser.add_argument("--url", default="", help="Presigned AgentCore WSS URL (optional if runtime ID/ARN is provided)")
    parser.add_argument("--runtime-id", default=os.getenv("AGENTCORE_RUNTIME_ID", ""), help="AgentCore runtime ID")
    parser.add_argument("--runtime-arn", default=os.getenv("AGENTCORE_RUNTIME_ARN", ""), help="AgentCore runtime ARN")
    parser.add_argument("--region", default=os.getenv("AWS_REGION", "us-east-1"), help="AWS region")
    parser.add_argument("--session-id", default="", help="Session ID override (default: random UUID)")
    parser.add_argument("--connect-timeout", type=float, default=15.0, help="WebSocket connect timeout seconds")
    parser.add_argument("--outbound-wait-seconds", type=float, default=8.0, help="How long to wait for outbound frames")
    parser.add_argument("--send-frames", type=int, default=3, help="Number of silence frames to send")
    parser.add_argument("--frame-bytes", type=int, default=640, help="Bytes per frame (Vonage 20ms PCM = 640)")
    parser.add_argument("--frame-interval-seconds", type=float, default=0.02, help="Delay between sent frames")
    parser.add_argument("--expect-outbound", action="store_true", help="Fail if no outbound frame is received")
    return parser.parse_args()


def load_env() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    load_dotenv(repo_root / ".env")


def build_presigned_url(args: argparse.Namespace) -> str:
    if args.url:
        return args.url

    if not args.runtime_id and not args.runtime_arn:
        raise ValueError("Provide --url or --runtime-id/--runtime-arn")

    try:
        import boto3
        from bedrock_agentcore.runtime import AgentCoreRuntimeClient
    except ImportError as exc:
        raise RuntimeError("boto3 and bedrock-agentcore are required to generate a presigned URL") from exc

    session_id = args.session_id or str(uuid.uuid4())

    # Resolve ARN: if only runtime_id given, build the full ARN
    runtime_arn = args.runtime_arn
    if not runtime_arn and args.runtime_id:
        sts = boto3.client("sts", region_name=args.region)
        account_id = sts.get_caller_identity()["Account"]
        runtime_arn = f"arn:aws:bedrock-agentcore:{args.region}:{account_id}:runtime/{args.runtime_id}"

    # AgentCoreRuntimeClient generates wss://.../runtimes/{arn}/ws — the correct WebSocket path
    client = AgentCoreRuntimeClient(region=args.region)
    return client.generate_presigned_url(runtime_arn, session_id=session_id)


async def run_websocket_probe(args: argparse.Namespace, ws_url: str) -> dict[str, Any]:
    try:
        import websockets
    except ImportError as exc:
        raise RuntimeError("websockets package is required for c6 probe") from exc

    report: dict[str, Any] = {
        "stage": "c6_agentcore_ws_serializer_smoke",
        "ws_url_prefix": ws_url[:80],
        "connected": False,
        "frames_sent": 0,
        "outbound_messages": 0,
        "outbound_binary_bytes": 0,
        "outbound_text_messages": 0,
        "errors": [],
    }

    silence_frame = b"\x00" * max(1, args.frame_bytes)

    try:
        async with websockets.connect(
            ws_url,
            open_timeout=max(1.0, args.connect_timeout),
            ping_interval=None,
            max_size=None,
        ) as ws:
            report["connected"] = True

            for _ in range(max(0, args.send_frames)):
                await ws.send(silence_frame)
                report["frames_sent"] += 1
                await asyncio.sleep(max(0.0, args.frame_interval_seconds))

            loop = asyncio.get_running_loop()
            end_at = loop.time() + max(0.0, args.outbound_wait_seconds)
            while loop.time() < end_at:
                remaining = end_at - loop.time()
                if remaining <= 0:
                    break
                try:
                    message = await asyncio.wait_for(ws.recv(), timeout=min(1.0, remaining))
                except asyncio.TimeoutError:
                    continue

                report["outbound_messages"] += 1
                if isinstance(message, (bytes, bytearray)):
                    report["outbound_binary_bytes"] += len(message)
                elif isinstance(message, str):
                    report["outbound_text_messages"] += 1

    except Exception as exc:
        report["errors"].append(str(exc))

    return report


def evaluate(report: dict[str, Any], expect_outbound: bool) -> tuple[bool, str]:
    if not report.get("connected"):
        return False, "failed_to_connect"
    if report.get("frames_sent", 0) <= 0:
        return False, "no_frames_sent"
    if expect_outbound and report.get("outbound_binary_bytes", 0) <= 0:
        return False, "no_outbound_binary"
    if report.get("errors"):
        return False, "runtime_error"
    return True, "passed"


def main() -> int:
    load_env()
    args = parse_args()

    try:
        ws_url = build_presigned_url(args)
    except Exception as exc:
        print(json.dumps({
            "stage": "c6_agentcore_ws_serializer_smoke",
            "status": "failed",
            "reason": "presigned_url_error",
            "error": str(exc),
        }, indent=2))
        return 2

    try:
        report = asyncio.run(run_websocket_probe(args, ws_url))
    except Exception as exc:
        print(json.dumps({
            "stage": "c6_agentcore_ws_serializer_smoke",
            "status": "failed",
            "reason": "probe_execution_error",
            "error": str(exc),
        }, indent=2))
        return 3

    passed, reason = evaluate(report, args.expect_outbound)
    result = {
        **report,
        "status": "passed" if passed else "failed",
        "reason": reason,
        "expect_outbound": bool(args.expect_outbound),
    }
    print(json.dumps(result, indent=2))
    return 0 if passed else 4


if __name__ == "__main__":
    raise SystemExit(main())
