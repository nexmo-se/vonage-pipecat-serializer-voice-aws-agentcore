#!/usr/bin/env python3
"""Local HTTP server wrapping lambda/answer.py for ngrok testing.

Exposes GET /answer → calls answer.handler → returns NCCO.

Used when Lambda Function URL is not reachable (e.g. org SCP blocks public
lambda:InvokeFunctionUrl). Run this locally + ngrok, then set Vonage
Answer URL to https://<ngrok-id>.ngrok.io/answer.

Usage:
    cd lambda/
    pip install fastapi uvicorn bedrock-agentcore
    AGENTCORE_RUNTIME_ARN=<arn> VONAGE_NUMBER=<number> AWS_PROFILE=vonage-dev \\
        uvicorn server:app --host 0.0.0.0 --port 3000

Then in another terminal:
    ngrok http 3000
"""

from __future__ import annotations

import json

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

import answer as answer_handler

app = FastAPI(title="vonage-answer-local")


@app.get("/answer")
async def vonage_answer(request: Request) -> JSONResponse:
    """Vonage GET /answer webhook — wraps lambda/answer.handler."""
    event = {"requestContext": {"http": {"method": "GET"}}}
    result = answer_handler.handler(event, None)
    return JSONResponse(
        content=json.loads(result["body"]),
        status_code=result["statusCode"],
        headers={k: v for k, v in result.get("headers", {}).items()},
    )


@app.get("/")
async def health() -> dict:
    return {"status": "ok", "note": "Vonage /answer local server — routes to AgentCore Runtime"}
