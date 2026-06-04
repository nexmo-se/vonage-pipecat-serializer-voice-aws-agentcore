# c8_runtime_end_to_end_single_call

## Status: PASSED

## Goal

Validate full single-call flow: simulated Vonage WebSocket client → AgentCore Runtime `/ws` → Pipecat pipeline → Nova Sonic.

## What was tested

A WebSocket probe connected to the deployed `vonage_runtime_agent` runtime via presigned URL,
sent a Vonage JSON connected header + PCM16 audio, and waited for Nova Sonic to return audio.

**Deployed runtime:** `vonage_runtime_agent-GC5gEQBPPz` (Python 3.12, us-east-1)

## Deploy the runtime

```bash
cd runtime/
PATH="$HOME/.local/bin:$PATH" AWS_PROFILE=vonage-dev agentcore deploy
# Uses .bedrock_agentcore.yaml config in runtime/

# Check status
PATH="$HOME/.local/bin:$PATH" AWS_PROFILE=vonage-dev agentcore status
```

## Run the test

```bash
cd <repo-root>
AWS_PROFILE=vonage-dev python tests2/c8_runtime_end_to_end_single_call/test_c8_runtime_end_to_end_single_call.py
```

Expected output:
```json
{
  "stage": "c8_runtime_end_to_end_single_call",
  "checks": {
    "websocket_connected": "PASS",
    "audio_frames_sent": "PASS (150 frames)",
    "nova_sonic_audio_received": "PASS (640 bytes)",
    "no_fatal_errors": "PASS"
  },
  "summary": { "passed": 4, "failed": 0 },
  "status": "PASS"
}
```

## Check CloudWatch logs

```bash
# Tail live logs
AWS_PROFILE=vonage-dev aws logs tail \
  "/aws/bedrock-agentcore/runtimes/vonage_runtime_agent-GC5gEQBPPz-DEFAULT" \
  --log-stream-name-prefix "$(date -u +%Y/%m/%d)/[runtime-logs" \
  --follow --region us-east-1

# Get most recent log stream name
AWS_PROFILE=vonage-dev aws logs describe-log-streams \
  --log-group-name "/aws/bedrock-agentcore/runtimes/vonage_runtime_agent-GC5gEQBPPz-DEFAULT" \
  --order-by LastEventTime --descending --max-items 5 --region us-east-1 \
  --query 'logStreams[0].logStreamName'

# Read full log stream (replace stream name with output from above)
AWS_PROFILE=vonage-dev aws logs get-log-events \
  --log-group-name "/aws/bedrock-agentcore/runtimes/vonage_runtime_agent-GC5gEQBPPz-DEFAULT" \
  --log-stream-name "<stream-name>" \
  --region us-east-1 \
  --query 'events[].message'
```

## Pass Results

| Check | Status |
|---|---|
| WebSocket connected to AgentCore presigned URL | PASS |
| 150 PCM16 audio frames sent (3s at 20ms/frame, 16kHz) | PASS |
| Nova Sonic returned audio bytes (640 bytes) | PASS |
| No fatal pipeline errors | PASS |

## Key Findings

### Dependencies (critical)
- `pipecat-ai[aws-nova-sonic,websocket]>=1.3.0` — the `aws-nova-sonic` extra installs `aws_sdk_bedrock_runtime`, which PyPI metadata restricts to **Python >= 3.12** only. On Python 3.11 the package installs silently without it.
- Runtime must run **Python 3.12** (`runtime_type: PYTHON_3_12` in `.bedrock_agentcore.yaml`).
- `[websocket]` extra is required for `FastAPIWebsocketTransport`.

Verified with:
```bash
curl -s https://pypi.org/pypi/pipecat-ai/1.3.0/json | python3 -c "
import json, sys
for r in json.load(sys.stdin)['info']['requires_dist']:
    if 'aws-nova-sonic' in r or 'aws_sdk' in r.lower():
        print(r)
"
# → aws_sdk_bedrock_runtime~=0.4.0; python_version >= "3.12" and extra == "aws-nova-sonic"
```

### HTTP 1008 "write buffer limit exceeded" (observed, now explained)
- Observed on the first two probe attempts. CloudWatch showed:
  ```
  ERROR  Exception: No module named 'aws_sdk_bedrock_runtime'
  ERROR  In order to use AWS services, you need to `pip install pipecat-ai[aws-nova-sonic]`.
  ERROR  Missing dependency  error="Missing module: No module named 'aws_sdk_bedrock_runtime'"
  ```
  and later (after adding `aws-nova-sonic` but still on Python 3.11):
  ```
  ERROR  Exception: No module named 'fastapi'
  ERROR  In order to use FastAPI websockets, you need to `pip install pipecat-ai[websocket]`.
  ```
- `agent.py` calls `await websocket.accept()` before imports (by design), so the WebSocket was accepted but no one was consuming incoming frames. AgentCore closed the connection with 1008.
- **Root cause: missing modules in `requirements.txt`, not slow startup timing.**
- After fixing requirements, CloudWatch showed the pipeline fully ready (Silero loaded, Nova Sonic connected, `on_client_connected` fired) within ~5 seconds of container start.

### Probe startup delay
- The probe waits 15 seconds after connect before sending audio. This was added as a conservative buffer during investigation. The healthy container was observed to be pipeline-ready in ~5s; the 15s lower bound has not been tested.

### Nova Sonic timeout without initial message
- Without `BEDROCK_INITIAL_USER_MESSAGE`, Nova Sonic logged error code 532:
  ```
  InternalErrorCode=532::Timed out waiting for audio bytes or interactive content.
  Please ensure gaps between audio bytes and interactive content are less than 55 seconds.
  ```
- The probe sent a 440Hz sine tone. Whether Silero VAD passed this to Nova Sonic as speech was not confirmed from logs; the only observed outcome was the Nova Sonic 532 timeout.
- Setting a default `BEDROCK_INITIAL_USER_MESSAGE` in `agent.py` causes `LLMRunFrame` to be queued on `on_client_connected`, bypassing VAD and triggering Nova Sonic to generate a greeting immediately. This is what produced the audio response in the passing run.

### Bedrock model validation
- The execution role returns `AccessDeniedException` for `bedrock:GetFoundationModel`. The agent skips validation gracefully and continues. Observed in CloudWatch:
  ```
  WARNING  Bedrock model validation skipped  code=AccessDeniedException
  ```

### What this test did NOT confirm
- Real Vonage telephony connecting to AgentCore (a simulated probe was used).
- More than one audio frame returned from Nova Sonic (640 bytes = 1 frame received).
- Behaviour under full duplex speech (VAD-triggered turns).

## Scope

- WebSocket connect + Vonage JSON header exchange
- PCM16 audio ingestion + pipeline lifecycle
- Nova Sonic audio generation (one frame confirmed)
- Connection teardown

