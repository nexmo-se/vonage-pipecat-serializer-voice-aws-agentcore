"""App Runner /answer handler — generates AgentCore presigned WSS URL and returns Vonage NCCO.

Triggered by Vonage GET /answer webhook (App Runner or local dev via answer/server.py).
"""

from __future__ import annotations

import json
import os
import uuid


def handler(event: dict, context) -> dict:
    if event.get("requestContext", {}).get("http", {}).get("method") != "GET":
        return {"statusCode": 405, "body": "Method Not Allowed"}

    runtime_arn = os.environ["AGENTCORE_RUNTIME_ARN"]
    vonage_number = os.environ["VONAGE_NUMBER"]
    region = os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
    session_id = str(uuid.uuid4())

    # AgentCoreRuntimeClient generates wss://.../runtimes/{arn}/ws — the correct
    # WebSocket path. Do NOT use boto3.client(...).generate_presigned_url() which
    # produces an HTTPS POST URL that returns HTTP 405 for WebSocket upgrades.
    from bedrock_agentcore.runtime import AgentCoreRuntimeClient
    client = AgentCoreRuntimeClient(region=region)
    presigned_url = client.generate_presigned_url(runtime_arn, session_id=session_id)

    ncco = [{
        "action": "connect",
        "from": vonage_number,
        "endpoint": [{
            "type": "websocket",
            "uri": presigned_url,
            "content-type": "audio/l16;rate=16000",
        }],
    }]

    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(ncco),
    }
