# c5_pipecat_agentcore_ws — Reference + Analysis

**This folder is reference material only. It is not a test stage and is not executed by `run_all.py`.**

## What This Is

An exact copy of [`Vonage/pipecat-examples/aws-agentcore`](https://github.com/Vonage/pipecat-examples/tree/main/aws-agentcore) (BSD 2-Clause License).

This is the upstream example that is claimed to confirm Pipecat + WebSocket transport works with AgentCore Runtime. The purpose of this folder is to study that claim carefully before drawing conclusions about whether `VonageFrameSerializer + FastAPIWebsocketTransport` can work in the same setup.

## Contents (upstream, unmodified)

```
c5_pipecat_agentcore_ws/
├── README.md           ← this file (analysis layer added on top)
├── bot.py              ← upstream Pipecat bot (run standalone, NOT deployed to AgentCore)
├── pyproject.toml      ← upstream Python project deps
├── env.example         ← upstream env template
└── agents/
    ├── dummy_agent.py  ← DEPLOYED to AgentCore Runtime (the actual AgentCore entrypoint)
    ├── requirements.txt
    └── pyproject.toml
```

---

## Critical Architecture Finding

After studying the source, the claim needs careful qualification. **The architecture is NOT what c6 assumed.**

### What the upstream example actually does

```
Vonage client
    │
    │  (WebSocket)
    ▼
bot.py  ←── runs standalone as a FastAPI/uvicorn server (NOT inside AgentCore Runtime)
    │         FastAPIWebsocketParams (twilio transport preset)
    │         or DailyParams / WebRTC
    │
    │  (HTTP POST — AWSAgentCoreProcessor.invoke)
    ▼
AgentCore Runtime  ←── dummy_agent.py or code_agent.py DEPLOYED HERE
    │                   BedrockAgentCoreApp entrypoint
    │                   handles text prompts, returns streamed responses
    ▼
Claude 3.7 Sonnet (via Bedrock)
```

### What this means

**AgentCore Runtime is used as the LLM/agent backend, invoked over HTTP.** It is not the WebSocket host. The Pipecat bot (`bot.py`) runs as a separate server that:

1. Accepts WebSocket connections from clients
2. Runs a full STT → AgentCore → TTS pipeline
3. Calls AgentCore via `AWSAgentCoreProcessor` (HTTP POST to the runtime's `/invocations` endpoint)

The WebSocket transport (`FastAPIWebsocketTransport`) lives in `bot.py`, which runs **outside** AgentCore Runtime.

### What c6 assumed (incorrectly — and was then proven correct by a different mechanism)

c6 initially tried to deploy a Pipecat bot with `VonageFrameSerializer + FastAPIWebsocketTransport` **inside** AgentCore Runtime as the entrypoint — expecting AgentCore to expose a WebSocket port.

**Initial wrong finding:** `HTTP 405 — Method Not Allowed. Use POST.` — because the probe was using the wrong AWS API and hitting `/invocations` instead of `/ws`.

**Actual finding after c6 was fixed:**

`BedrockAgentCoreApp` (from the `bedrock-agentcore` SDK) exposes **THREE routes**:
- `POST /invocations` — standard HTTP invoke
- `GET /ping` — health check
- **`WebSocket /ws`** — WebSocket endpoint via `WebSocketRoute("/ws", ...)`

AgentCore Runtime **does** proxy WebSocket connections from `wss://bedrock-agentcore.{region}.amazonaws.com/runtimes/{arn}/ws` to the container's `/ws` endpoint. The c6 test **PASSED** — see the c6 README for the confirmed test result.

This means the Glean AI Options A and B architecture **is architecturally sound**:
```
Vonage Voice API
→ Lambda /answer → returns NCCO with presigned wss://.../ws URL
→ AgentCore Runtime /ws → VonageFrameSerializer + FastAPIWebsocketTransport → Pipecat
```

**Key implementation requirement:** The `@app.websocket` handler in `bot.py` must call `await websocket.accept()` before using `FastAPIWebsocketTransport`. `BedrockAgentCoreApp` does not auto-accept the WebSocket before calling the handler.

---

## Revised Conclusion After c6 Passed

**`VonageFrameSerializer + FastAPIWebsocketTransport` CAN work inside AgentCore Runtime.**

This means the Glean AI Options A and B are viable. Vonage can connect directly to an AgentCore Runtime via a presigned WebSocket URL. The main app's FastAPI server does **not** need to be hosted separately — AgentCore Runtime can be the WebSocket host.

The correct production architecture (Options A/B):

```
Vonage Voice call
    │
    │  GET /answer  (returns NCCO)
    ▼
Lambda Function URL  ←── generates presigned wss://.../runtimes/{arn}/ws URL
    │
    │  wss://.../runtimes/{arn}/ws  (Vonage Audio Connector WebSocket)
    ▼
AgentCore Runtime  ←── BedrockAgentCoreApp /ws
    │                   VonageFrameSerializer + FastAPIWebsocketTransport
    │                   Pipecat pipeline (+ Nova Sonic or other LLM)
    ▼
(AI backend — Bedrock, Nova Sonic, etc.)
```

The current main app (`agent.py` + `main.py`) works correctly for local dev and can be adapted for AgentCore by wrapping with `BedrockAgentCoreApp`.

## Reference: vonage-audio-bot

`Vonage/pipecat-examples/vonage-audio-bot` is the most directly relevant upstream reference. It shows `VonageFrameSerializer + FastAPIWebsocketTransport` wired in exactly the same pattern as the main app — with a standalone FastAPI server receiving Vonage Audio Connector WebSocket connections. It uses OpenAI for STT/LLM/TTS; the main app uses Nova Sonic + AgentCore.

See: [`Vonage/pipecat-examples/vonage-audio-bot`](https://github.com/Vonage/pipecat-examples/tree/main/vonage-audio-bot)
