# vonage-pipecat-serializer-voice-aws-agentcore

Real-time voice agent using **Vonage Audio Serializer for Pipecat** with **AWS Bedrock Nova Sonic** and optional **AWS AgentCore bootstrap**.

## Overview and architecture

This application implements a speech-to-speech AI voice agent that connects Vonage Voice API calls to a Pipecat processing pipeline via the **Vonage Audio Serializer** — a WebSocket-based transport optimized for audio-only Pipecat pipelines per [official Vonage guidance](https://developer.vonage.com/en/video/guides/vonage-pipecat-serializer-overview).

Runtime path:

```text
Vonage Voice Call (Media)
  ↓ WebSocket Audio Stream
Vonage Audio Serializer Transport
  ↓
Pipecat Processing Pipeline
  ↓
AWS Bedrock Nova Sonic (Speech-to-Speech LLM)
  ↓
Pipecat Output Serialization
  ↓ WebSocket Audio Response
Vonage Voice Call (Media)
```

**Audio-only architecture:** This application uses the Vonage Audio Serializer Transport (WebSocket-based), not the Video Connector Transport (WebRTC-based). This is the recommended approach for audio-only speech AI applications.

AgentCore remains an optional bootstrap layer used at startup to prime assistant behavior.

## Prerequisites and setup

- Python 3.13+
- Vonage application credentials and `private.key`
- AWS credentials with Bedrock (and AgentCore if enabled)
- Docker (recommended for consistent environment)

Setup:

```bash
cp .env.example .env
# update .env values
```

## Environment variables

Primary variables:

- `VONAGE_APPLICATION_ID`
- `VONAGE_PRIVATE_KEY`
- `VONAGE_CALL_ID`
- `AWS_PROFILE` / `AWS_REGION`
- `BEDROCK_MODEL_ID`
- `AGENTCORE_AGENT_ARN` (optional)
- `PORT`

## Run instructions

### App (Docker)

```bash
docker compose --profile app up --build app
```

### App (native)

```bash
cd app
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000
```

## Test instructions

Run staged tests in order to validate each layer of the architecture:

1. **C1 — Voice Call Bootstrap** (`tests/c1_voice_call_bootstrap`)
   - Creates a new Vonage voice session
   - Generates a call ID and publisher token
   - Validates Vonage credentials and API access
   - Saves call ID to `.env` for subsequent tests

2. **C2 — Audio Serializer Connectivity** (`tests/c2_voice_linux_sdk`)
   - Tests Vonage Audio Serializer transport connection
   - Validates WebSocket bridge to Vonage Voice API
   - Confirms audio serialization layer is functional
   - Uses the call session from C1

3. **C3 — Pipecat Serializer Echo** (`tests/c3_pipecat_serializer`)
   - Runs a Pipecat pipeline that echoes audio back
   - Validates serializer transport and event lifecycle
   - Confirms audio frame orchestration works

4. **C4a — Bedrock Preflight** (`tests/c4a_bedrock_preflight`)
   - Verifies AWS Bedrock credentials and model access
   - Tests Nova Lite text inference for quick validation
   - Checks integration module loads correctly

5. **C4b — Bedrock Nova Sonic + Serializer** (`tests/c4b_bedrock_nova_sonic_serializer`)
   - Full integration test: Audio Serializer + Nova Sonic LLM
   - Validates end-to-end speech-to-speech pipeline
   - Tests LLM context management and response generation

6. **C5 — AgentCore Runtime** (`tests/c5_agentcore_runtime`)
   - Tests optional AWS Bedrock AgentCore bootstrap
   - Validates agent runtime invocation
   - Requires valid AgentCore ARN and deployment

Each test includes detailed run instructions, expected output, and troubleshooting in its folder's README. Start with C1 and proceed sequentially.

## Validation steps

```bash
curl http://localhost:8000/
curl http://localhost:8000/status
```

Join/leave API:

```bash
curl -X POST http://localhost:8000/join -H "Content-Type: application/json" -d '{"call_id":"'$VONAGE_CALL_ID'"}'
curl -X POST http://localhost:8000/leave
```

## Production notes

- Use Linux-based runtime for Voice SDK compatibility.
- Prefer IAM roles over static AWS keys.
- Keep credentials/secrets outside repository and container images.
- Tune Bedrock timeout/retry env vars for latency and resilience.
