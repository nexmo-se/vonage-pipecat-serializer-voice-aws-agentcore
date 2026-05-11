# C4b — Bedrock Nova Sonic + Audio Serializer

Full integration test: Vonage Audio Serializer Transport + Pipecat + AWS Bedrock Nova Sonic speech-to-speech processing.

> **Architecture:** Incoming voice from Vonage Voice API → Audio Serializer Transport → Pipecat pipeline → AWS Bedrock Nova Sonic LLM → Response audio → Back to Vonage call

## Prerequisites

1. **✅ C4a PASSED** — AWS Bedrock credentials and Nova Lite validation confirmed
2. **✅ C1 Call Active** — `VONAGE_CALL_ID` in `.env` (from C1 test, valid for ~1 hour)
3. **Python 3.14+** with venv support
4. **AWS Bedrock Nova Sonic Model** — `amazon.nova-2-sonic-v1:0` enabled on your account
5. **Network**: Vonage Voice API connectivity + AWS Bedrock API access

## Quick Start

### 1. Validation Tests

Verify C4b setup before running live agent:

```bash
cd tests/c4b_bedrock_nova_sonic_serializer
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\\Scripts\\activate

# Install dependencies (skip Pipecat, install only what's needed)
pip install 'boto3>=1.34.0' 'loguru>=0.7.0' 'python-dotenv>=1.2.2' \
  'vonage>=4.8.0' 'websockets>=15.0.0' 'fastapi>=0.110.0' 'uvicorn[standard]>=0.29.0'

# Run Bedrock Nova Sonic validation
python test_bedrock.py

# Test Bedrock + Audio Serializer integration
python test_integration.py
```

### 2. Live Speech-to-Speech Agent

Once tests pass, start the live agent:

```bash
# With AWS profile
AWS_PROFILE=vonage-dev python bedrock_echo_agent.py

# Or with explicit credentials
export AWS_ACCESS_KEY_ID=your-key
export AWS_SECRET_ACCESS_KEY=your-secret
python bedrock_echo_agent.py
```

### 3. Docker Deployment (Recommended)

```bash
cd /path/to/repo
AWS_PROFILE=vonage-dev docker compose run --rm c4b-bedrock-nova-sonic-serializer
```

## Expected Output

### Validation Tests Pass

```bash
# test_bedrock.py
✓ Using AWS profile: vonage-dev (region: us-east-1)
✓ Bedrock client initialised
✓ Model access verified: amazon.nova-2-sonic-v1:0

Sending test prompt: "Hello, I am testing speech-to-speech."
✓ Response received:
  Hello! I'm ready to help. What would you like to test?

Test C4b PASSED ✓

# test_integration.py
✓ Bedrock + Audio Serializer integration verified
✓ Pipeline initialization successful
✓ Frame processing verified
Integration test PASSED ✓
```

### Live Agent Startup

```bash
2026-05-11 14:32:15.890 | INFO | pipecat:<module>:14 - ᓚᘏᗢ Pipecat 0.0.104.post2.dev1

Bedrock Nova Sonic + Audio Serializer Speech-to-Speech Agent
  Call ID: <VONAGE_CALL_ID>
  Model: amazon.nova-2-sonic-v1:0 (speech-to-speech)
  Transport: Vonage Audio Serializer (WebSocket)
  Listening on ws://0.0.0.0:8000/ws

✓ Agent initialized and ready
✓ Joined Vonage call successfully
✓ Listening for incoming audio...

Press Ctrl+C to disconnect and exit
```

### During Live Conversation

```
[14:32:30] Received audio frame (PCM 16kHz, 320 bytes)
[14:32:31] Processing audio through pipeline...
[14:32:32] Bedrock inference complete
[14:32:32] Sending response audio to caller...
[14:32:35] Received audio frame (PCM 16kHz, 320 bytes)
...
```

## Architecture: Speech-to-Speech Pipeline

```
Vonage Voice API (inbound call)
           ↓
    WebSocket (NCCO connect)
           ↓
    Audio Serializer Transport
    (receives PCM 16-bit, 16kHz)
           ↓
    Pipecat Pipeline
           ↓
    AWS Bedrock Nova Sonic
    (speech-to-speech LLM)
           ↓
    Speech Output Serializer
           ↓
    Audio Serializer Transport
    (sends PCM audio back)
           ↓
    Vonage → Caller (audio response)
```

## Processing Stages

| Stage             | Component               | Function                                                          |
| ----------------- | ----------------------- | ----------------------------------------------------------------- |
| **Audio Receive** | Vonage Audio Serializer | Accepts incoming audio frames from Voice API                      |
| **Pipeline**      | Pipecat Runner          | Orchestrates frame processing                                     |
| **LLM**           | AWS Bedrock Nova Sonic  | Converts speech→text, generates response, converts back to speech |
| **Audio Send**    | Vonage Audio Serializer | Serializes response audio and sends to caller                     |
| **Context**       | LLM Message Buffer      | Maintains conversation history for multi-turn dialogue            |

## Test findings

- ✅ Vonage Audio Serializer Transport integration with Pipecat
- ✅ AWS Bedrock Nova Sonic invocation and response handling
- ✅ Audio serialization/deserialization with correct format conversion
- ✅ Real-time speech-to-speech processing latency
- ✅ LLM context and conversation history management
- ✅ Error handling and graceful shutdown

## Troubleshooting

| Issue                                       | Root Cause                                 | Solution                                                                             |
| ------------------------------------------- | ------------------------------------------ | ------------------------------------------------------------------------------------ |
| `Bedrock access denied`                     | Missing IAM permissions or wrong region    | Re-run C4a test; verify `bedrock:InvokeModel` permission                             |
| `Model not found: amazon.nova-2-sonic-v1:0` | Model unavailable in region                | Ensure Nova Sonic is available in `us-east-1` on your account                        |
| `VONAGE_CALL_ID missing`                    | C1 test not run or expired                 | Re-run C1 test: `cd tests/c1_voice_call_bootstrap && python test_voice_bootstrap.py` |
| `Connection refused on port 8000`           | Port already in use                        | Use different port: `WS_PORT=8001 python bedrock_echo_agent.py`                      |
| `No audio being received`                   | Call not active or WebSocket not connected | Verify call is active; check that NCCO is routing to correct WebSocket endpoint      |
| `Import errors (onnxruntime, pipecat)`      | Dependency conflict                        | Install only required packages (skip Pipecat full install)                           |
| `Script hangs on initialization`            | Network timeout or authentication delay    | Check AWS connectivity; allow 10-30s for pipeline startup                            |
| `Ctrl+C doesn't exit cleanly`               | Signal handling issue                      | Use `Ctrl+C` multiple times or kill terminal session                                 |

## Next Steps

Once C4b **PASSES**:

- ✅ Speech-to-speech pipeline validated
- ✅ Audio streaming working end-to-end
- ✅ Nova Sonic inference operational
- **→ Proceed to C5:** AgentCore runtime integration (optional)
- **→ Or go to app/:** Full production deployment
