# c6_agentcore_ws_serializer_smoke

## Status: ✅ PASSED

`VonageFrameSerializer + FastAPIWebsocketTransport` works inside AgentCore Runtime.

## Goal

Confirm the serializer + transport stack runs correctly when deployed inside AgentCore Runtime on port 8080 — the P0 blocker before building `runtime/agent.py`.

## Files

| File | Purpose |
|------|---------|
| `bot.py` | Minimal `BedrockAgentCoreApp` bot — deploy to AgentCore Runtime |
| `requirements.txt` | Bot dependencies (used by `agentcore deploy`) |
| `bot_requirements.txt` | Same deps, named for clarity |
| `test_c6_agentcore_ws_serializer_smoke.py` | Probe — runs locally, connects to deployed runtime |

## Test Result

**Runtime:** `arn:aws:bedrock-agentcore:us-east-1:589536902306:runtime/c6_agentcore_ws_serializer-4XCZ6u4v5G`

**Probe output:**
```json
{
  "connected": true,
  "frames_sent": 10,
  "status": "passed"
}
```

**CloudWatch logs confirmed:**
```
INFO  WebSocket connection received via BedrockAgentCoreApp /ws
INFO  Client connected — VonageFrameSerializer active
INFO  First inbound audio frame received
INFO  Client disconnected
```

## Key Implementation Details

**`websocket.accept()` is required.** `BedrockAgentCoreApp` routes to your handler without accepting first. Add `await websocket.accept()` as the first line of `@app.websocket`.

**Use `AgentCoreRuntimeClient` for presigned URLs**, not the raw boto3 client:
```python
from bedrock_agentcore.runtime import AgentCoreRuntimeClient
client = AgentCoreRuntimeClient(region="us-east-1")
url = client.generate_presigned_url(runtime_arn, session_id=session_id)
# → wss://bedrock-agentcore.us-east-1.amazonaws.com/runtimes/{arn}/ws?...
```

**`pipecat-ai>=1.3.0` from PyPI** includes `VonageFrameSerializer` — no Vonage fork needed.

## Deploy (for reference / re-running)

```bash
cd tests2/c6_agentcore_ws_serializer_smoke
agentcore deploy   # uses .bedrock_agentcore.yaml config
```

## Run Probe

```bash
pip install bedrock-agentcore websockets python-dotenv

python tests2/c6_agentcore_ws_serializer_smoke/test_c6_agentcore_ws_serializer_smoke.py \
    --runtime-arn "arn:aws:bedrock-agentcore:us-east-1:<account>:runtime/<id>" \
    --send-frames 10
```

## Pass Criteria

- WebSocket connects successfully
- At least one inbound binary PCM frame processed by `VonageFrameSerializer`
- Clean disconnect — no exceptions

> **Note:** No `--expect-outbound`. Silence frames don't trigger TTS output. Inbound deserialization is what's validated here; the full audio round-trip is c8's job.

