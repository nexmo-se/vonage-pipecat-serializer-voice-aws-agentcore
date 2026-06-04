# c5_pipecat_agentcore_ws — Reference

**Reference material only — not a test stage, not executed by `run_all.py`.**

## What This Is

An exact copy of [`Vonage/pipecat-examples/aws-agentcore`](https://github.com/Vonage/pipecat-examples/tree/main/aws-agentcore) (BSD 2-Clause License).

Used as a reference baseline to understand how `BedrockAgentCoreApp` and AgentCore Runtime work before building `runtime/agent.py`.

## Contents (upstream, unmodified)

```
c5_pipecat_agentcore_ws/
├── bot.py              ← Pipecat bot — runs STANDALONE, calls AgentCore over HTTP
├── pyproject.toml
├── env.example
└── agents/
    ├── dummy_agent.py  ← DEPLOYED to AgentCore Runtime (BedrockAgentCoreApp entrypoint)
    ├── requirements.txt
    └── pyproject.toml
```

## Architecture of the Upstream Example

```
Vonage/WebRTC client
    │  WebSocket
    ▼
bot.py  — standalone FastAPI/uvicorn server (NOT inside AgentCore)
    │  HTTP POST via AWSAgentCoreProcessor
    ▼
AgentCore Runtime  — dummy_agent.py deployed here
    │  BedrockAgentCoreApp, handles text prompts
    ▼
Claude 3.7 Sonnet (Bedrock)
```

**Key insight:** In this upstream example, `bot.py` runs *outside* AgentCore. AgentCore is the LLM backend, called over HTTP. The WebSocket lives in `bot.py`, not in AgentCore.

## What BedrockAgentCoreApp Actually Exposes

The `bedrock-agentcore` SDK's `BedrockAgentCoreApp` is a Starlette app that exposes three routes on port 8080:

| Route | Method | Purpose |
|-------|--------|---------|
| `/invocations` | POST | Standard HTTP invoke |
| `/ping` | GET | Health check |
| `/ws` | WebSocket | WebSocket endpoint — `@app.websocket` handler |

AgentCore Runtime proxies `wss://bedrock-agentcore.{region}.amazonaws.com/runtimes/{arn}/ws` directly to the container's `/ws` route. This was confirmed by [c6](../c6_agentcore_ws_serializer_smoke/README.md): a WebSocket probe connected, sent PCM frames, and `VonageFrameSerializer + FastAPIWebsocketTransport` processed them correctly inside the runtime container.

## Planned Production Architecture

> **Not yet end-to-end tested.** c6 confirmed the WebSocket/serializer layer. Lambda + actual Vonage call flow is validated by c7 and c8.

```
Vonage Voice call
    │  GET /answer
    ▼
Lambda Function URL  — generates presigned wss://.../runtimes/{arn}/ws
    │  wss://... (Vonage Audio Connector WebSocket)
    ▼
AgentCore Runtime  — BedrockAgentCoreApp @app.websocket /ws
    │  VonageFrameSerializer + FastAPIWebsocketTransport + Pipecat + Nova Sonic
    ▼
AWS Bedrock Nova Sonic
```

## Key Implementation Requirements

1. **`await websocket.accept()`** — must be the first call in `@app.websocket` handler. `BedrockAgentCoreApp` does not auto-accept.
2. **Presigned URL** — use `AgentCoreRuntimeClient.generate_presigned_url()` from the `bedrock-agentcore` SDK, not the raw boto3 client. Generates `wss://.../runtimes/{arn}/ws`.
3. **Port** — `app.run(port=8080)` — AgentCore Runtime requirement.
4. **Credentials** — IMDS inside the container; no `.env` or `AWS_PROFILE` needed.

## References

- [c6 smoke test — PASSED](../c6_agentcore_ws_serializer_smoke/README.md)
- [BedrockAgentCoreApp source](https://github.com/aws/bedrock-agentcore-sdk-python/blob/main/src/bedrock_agentcore/runtime/app.py)
- [vonage-audio-bot upstream example](https://github.com/Vonage/pipecat-examples/tree/main/vonage-audio-bot)

