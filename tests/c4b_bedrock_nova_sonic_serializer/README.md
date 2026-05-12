# C4b — Bedrock Nova Sonic + Audio Serializer

Full integration test: Vonage Audio Serializer Transport + Pipecat + AWS Bedrock Nova Sonic speech-to-speech processing.

> Architecture: Incoming phone call -> Vonage Voice API -> NCCO WebSocket connect -> this agent (FastAPI/Pipecat) -> AWS Bedrock Nova Sonic LLM -> audio response back to caller

## Prerequisites

1. C4a passed (AWS credentials + model validation)
2. Python 3.14+ with shared venv at `tests/c2_voice_linux_sdk/venv`
3. AWS Bedrock model access enabled for `amazon.nova-2-sonic-v1:0` in `us-east-1`
4. ngrok installed
5. Vonage application has a voice-enabled number linked

## Quick Start

### Step 1: Activate shared venv and install missing packages

```bash
cd tests/c4b_bedrock_nova_sonic_serializer
source ../c2_voice_linux_sdk/venv/bin/activate
pip install aws-sdk-bedrock-runtime aioboto3
```

### Step 2: Run validation tests (no live phone call needed)

```bash
python test_bedrock.py
python test_integration.py
```

### Step 3: Free port before starting live agent

If you see this error:

```text
ERROR: [Errno 48] error while attempting to bind on address ('0.0.0.0', 8001): address already in use
```

Clear the port first:

```bash
# Find process using 8001
lsof -iTCP:8001 -sTCP:LISTEN -n -P

# Kill it (replace <PID>)
kill <PID>

# One-liner alternative
lsof -ti tcp:8001 | xargs kill -9 2>/dev/null || true
```

### Step 4: Start live agent

```bash
WS_PORT=8001 AWS_PROFILE=vonage-dev python bedrock_echo_agent.py
```

Expected startup output:

```text
✓ AWS credentials resolved (profile: vonage-dev, region: us-east-1)

Bedrock Nova Sonic + Vonage Audio Serializer Agent
  Model:     amazon.nova-2-sonic-v1:0
  Region:    us-east-1
  Listening: ws://0.0.0.0:8001/ws
```

### Step 5: Expose with ngrok (second terminal)

```bash
ngrok http --domain=kittphi.ngrok.app 8001
```

If you do not have a reserved domain:

```bash
ngrok http 8001
```

### Step 6: Configure Vonage app URLs

In Vonage Dashboard -> Applications -> your app -> Edit:

1. Answer URL (GET): `https://kittphi.ngrok.app/answer`
2. Event URL: `https://kittphi.ngrok.app/`

Important: You do not configure `/ws` in the dashboard directly. The `/answer` endpoint returns NCCO that points Vonage to `wss://.../ws`.

### Step 7: Verify routing before calling

```bash
curl -s https://kittphi.ngrok.app/answer
```

Expected response includes:

- `"action":"connect"`
- `"uri":"wss://kittphi.ngrok.app/ws"` (or your current ngrok host)

If you get `{"detail":"Not Found"}`, your running process is stale. Restart the agent from this folder and try again.

### Step 8: Place a call

Call the voice-enabled Vonage number linked to this app (Dashboard -> Numbers -> Your numbers).

When connected, agent logs should show:

```text
Answer webhook called -> routing call to wss://.../ws
✓ Vonage connected: ...
✓ Listening for audio (Nova Sonic ready)...
```

## Troubleshooting

| Issue | Root Cause | Fix |
|---|---|---|
| `address already in use` | Previous process still bound to port | Run port-clear commands in Step 3 |
| `{"detail":"Not Found"}` at `/answer` | Old server process without `/answer` route | Kill old PID on 8001 and restart `bedrock_echo_agent.py` |
| `No module named 'aws_sdk_bedrock_runtime'` | Missing package | `pip install aws-sdk-bedrock-runtime aioboto3` |
| Bedrock access denied | IAM/region mismatch | Confirm profile and `us-east-1` model access |
| No audio after call connects | ngrok host mismatch or stale dashboard URL | Re-copy ngrok URL and update Answer URL |

## Next Steps

After C4b passes:

- Proceed to C5 (optional AgentCore runtime validation)
- Or continue to full app deployment in `app/`
