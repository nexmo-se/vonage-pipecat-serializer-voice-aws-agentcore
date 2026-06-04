# c6_agentcore_ws_serializer_smoke

## Goal

Confirm `VonageFrameSerializer + FastAPIWebsocketTransport` works correctly inside AgentCore Runtime on port 8080.

## Reference Baseline

`tests2/c5_pipecat_agentcore_ws/` contains the upstream [`pipecat-ai/pipecat-examples/aws-agentcore`](https://github.com/pipecat-ai/pipecat-examples/tree/main/aws-agentcore) source. That example establishes the baseline: raw `FastAPIWebsocketTransport` works inside an AgentCore Runtime deployment. c6 builds directly on that baseline — the only addition is wrapping the transport with `VonageFrameSerializer` to handle Vonage's binary PCM framing protocol.

If c6 fails, compare c6's runtime agent against `c5_pipecat_agentcore_ws/bot.py` to isolate whether the failure is serializer-specific or a deeper runtime/transport issue.

## Files

| File | Purpose |
|------|---------|
| `bot.py` | Runtime agent — deploy this to AgentCore Runtime |
| `bot_requirements.txt` | Dependencies for `bot.py` (installed inside the runtime image) |
| `requirements.txt` | Dependencies for the test probe (local) |
| `test_c6_agentcore_ws_serializer_smoke.py` | Test probe — runs locally, connects to the deployed runtime |

## Deploy bot.py to AgentCore Runtime

`bot.py` must be deployed before running the probe. It is a minimal FastAPI + uvicorn server that wires `FastAPIWebsocketTransport` with `VonageFrameSerializer` — no AI services.

```bash
cd tests2/c6_agentcore_ws_serializer_smoke

# Configure runtime (first time only)
agentcore configure -e bot.py -r us-east-1
# Select: Direct Code Deploy, Python 3.11, auto-create role and S3 bucket

# Deploy
agentcore deploy
```

Copy the runtime ARN from the deploy output and set it in repo root `.env`:

```bash
AGENTCORE_RUNTIME_ID=<your-runtime-id>
# or
AGENTCORE_RUNTIME_ARN=arn:aws:bedrock-agentcore:us-east-1:<account>:runtime/<id>
```

## Test Result: ✅ PASSED — VonageFrameSerializer + FastAPIWebsocketTransport works inside AgentCore Runtime

**Run date:** 2026-06-04

**Runtime deployed:** `arn:aws:bedrock-agentcore:us-east-1:589536902306:runtime/c6_agentcore_ws_serializer-4XCZ6u4v5G`

**Probe result:**
```json
{
  "stage": "c6_agentcore_ws_serializer_smoke",
  "connected": true,
  "frames_sent": 10,
  "status": "passed",
  "reason": "passed"
}
```

**CloudWatch confirmation:**
```
INFO  WebSocket connection received via BedrockAgentCoreApp /ws
INFO  Client connected — VonageFrameSerializer active
INFO  First inbound audio frame received
INFO  Client disconnected
```

**What this proves:**
- `BedrockAgentCoreApp` exposes `WebSocketRoute("/ws", ...)` on port 8080
- The AgentCore Runtime routes `wss://bedrock-agentcore.../runtimes/{arn}/ws` to the container's `/ws` endpoint
- `FastAPIWebsocketTransport + VonageFrameSerializer` successfully initializes and processes binary PCM frames inside AgentCore Runtime
- Clean session lifecycle (connect → receive frames → disconnect)

**Critical implementation detail:**
`BedrockAgentCoreApp` does NOT call `websocket.accept()` before routing to your handler.
You MUST call `await websocket.accept()` at the start of the `@app.websocket` handler — otherwise the pipeline starts, immediately detects a stale connection, and disconnects. This is consistent with how the main app's `agent.py` works (line ~138).

**Correct presigned URL generation:**
Use `AgentCoreRuntimeClient.generate_presigned_url()` from the `bedrock-agentcore` SDK (not the raw boto3 `bedrock-agentcore` client). This generates:
```
wss://bedrock-agentcore.{region}.amazonaws.com/runtimes/{encoded_arn}/ws?...
```
The old approach of using `boto3.client(...).generate_presigned_url('invoke_agent_runtime', ...)` generates an HTTPS POST URL which returns HTTP 405.

**Previous wrong finding (retracted):**
An earlier version of this README stated AgentCore Runtime does not support WebSocket. That was wrong — the probe was hitting the wrong endpoint (`/invocations` instead of `/ws`) using the wrong API.

## Scope

- WebSocket connect and upgrade path
- Audio frame ingress/egress through serializer
- Clean disconnect and task teardown

## Pass Criteria

- Runtime accepts Vonage WebSocket connection on the expected route.
- At least one inbound binary frame is accepted without a serializer/transport exception.
- Clean disconnect after probe completes.

> **Note:** `--expect-outbound` is intentionally not used here. The probe sends PCM silence frames which will not trigger TTS output (there is no AI pipeline in `bot.py`). The smoke test validates inbound deserialization only — the outbound path is covered by the full end-to-end test in c8.

## Required Inputs

Provide one of the following:

- A presigned websocket URL via `--url`
- Or AgentCore runtime identity via `--runtime-id` (or `--runtime-arn`) and AWS credentials

Environment variables supported:

- `AWS_REGION`
- `AGENTCORE_RUNTIME_ID`
- `AGENTCORE_RUNTIME_ARN`

## Run

```bash
# Install test probe deps
python -m pip install -r tests2/c6_agentcore_ws_serializer_smoke/requirements.txt

# Option A: use runtime ID/ARN (presigned URL generated automatically)
python tests2/c6_agentcore_ws_serializer_smoke/test_c6_agentcore_ws_serializer_smoke.py \
    --runtime-id "$AGENTCORE_RUNTIME_ID" \
    --region us-east-1

# Option B: use a pre-generated presigned URL
python tests2/c6_agentcore_ws_serializer_smoke/test_c6_agentcore_ws_serializer_smoke.py \
    --url "wss://..."
```

## Notes

- The probe sends 640-byte PCM silence frames (20 ms at 16 kHz mono) — matching Vonage's wire format.
- Do not use `--expect-outbound`: silence frames do not trigger pipeline output. Inbound serialization is the only thing being validated here.
- `bot.py` mirrors the main app's `agent.py` transport setup exactly, minus all AI services. If c6 fails, diff `bot.py` against `c5_pipecat_agentcore_ws/bot.py` (no serializer) to isolate whether the failure is serializer-specific.
- Use this stage as the P0 blocker before any main app modifications.
