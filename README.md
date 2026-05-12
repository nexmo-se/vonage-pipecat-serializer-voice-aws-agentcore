# vonage-pipecat-serializer-voice-aws-agentcore

Reference implementation of a **production-ready voice AI agent** combining:

- **Vonage Audio Serializer for Pipecat** — WebSocket transport for real-time phone call audio
- **AWS Bedrock Nova Sonic** — Speech-to-speech conversational AI (no transcription needed)
- **AWS Bedrock AgentCore** — Agent runtime for tool use, knowledge bases, and real-world actions

> **The showcase:** This repo demonstrates how to connect a live Vonage phone call all the way through to an AWS-hosted AI agent that can converse in real time _and_ take actions — using the Vonage Pipecat Serializer as the bridge.

## Why This Stack?

| Layer                       | What it solves                                                                                           |
| --------------------------- | -------------------------------------------------------------------------------------------------------- |
| **Vonage Audio Serializer** | Bridges phone call audio (WebSocket PCM) into a Pipecat pipeline without WebRTC complexity               |
| **Nova Sonic**              | Eliminates the STT → LLM → TTS chain — processes voice end-to-end with sub-second latency                |
| **AgentCore**               | Gives the voice agent real-world capabilities: call a weather API, query a knowledge base, look up a CRM |

Without AgentCore, you get a smart conversational assistant limited to its training data. With AgentCore, you get an agent that can **do things** — answer questions from your own docs, book appointments, check order status — all over a live phone call.

## Architecture

```text
Caller dials Vonage number
  ↓
Vonage Voice API
  ↓ WebSocket (PCM 16-bit, 16kHz)
Vonage Audio Serializer Transport  ←── Pipecat's WebSocket bridge for phone audio
  ↓
Pipecat Pipeline
  ↓
AWS Bedrock Nova Sonic             ←── Speech-to-speech LLM (voice in, voice out)
  ↓ (when tools/knowledge needed)
AWS Bedrock AgentCore              ←── Agent runtime: tools, RAG, external APIs
  ↓
Audio response streams back to caller
```

**Audio-only design:** Uses the Vonage Audio Serializer (WebSocket), not the Video Connector (WebRTC). This is the recommended approach for voice-only AI per [official Vonage guidance](https://developer.vonage.com/en/video/guides/vonage-pipecat-serializer-overview).

## Prerequisites and setup

- Docker
- AWS credentials with Bedrock access (and AgentCore if enabled)
- ngrok account with reserved domain (recommended for stable Vonage webhook URL)
- Vonage Voice application configured with a public Answer URL

Setup:

```bash
cp .env.example .env
# update .env values
```

## Environment variables

Primary variables for the main app (`app/`):

- `AWS_PROFILE` / `AWS_REGION`
- `BEDROCK_MODEL_ID`
- `AGENTCORE_AGENT_ARN` (optional)
- `PORT`

Note: The production `app/` webhook flow does not require `VONAGE_CALL_ID` or Vonage Video SDK credentials. Vonage calls `/answer`, receives NCCO, then connects media to `/ws`.

## Run instructions

### App (Docker - recommended)

```bash
# run from repository root
docker compose --profile app up --build app
```

The app is intended to run in Docker for an isolated, reproducible runtime independent from test folders.

### Expose app with ngrok

```bash
ngrok http --domain=kittphi.ngrok.app 8000
```

Set Vonage Answer URL to:

```text
https://kittphi.ngrok.app/answer
```

Expected flow:

1. Vonage requests `/answer`
2. App returns NCCO with `wss://kittphi.ngrok.app/ws`
3. Vonage streams call audio over WebSocket to `/ws`

## Test instructions

The `tests/` folders are proof-of-components layers used during development.
They are not required to run the production `app/` service.

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
   - Validates AgentCore runtime invocation from the voice pipeline
   - Confirms the agent can call tools and return structured responses
   - Required for production agents that need real-world actions or private knowledge

Each test includes detailed run instructions, expected output, and troubleshooting in its folder's README. Start with C1 and proceed sequentially.

## Validation steps

```bash
curl http://localhost:8000/
curl http://localhost:8000/status
```

NCCO + call control API:

```bash
curl -H "Host: kittphi.ngrok.app" https://kittphi.ngrok.app/answer
curl -X POST http://localhost:8000/hangup
```

## Production notes

- Use Linux-based runtime for Voice SDK compatibility.
- Prefer IAM roles over static AWS keys.
- Keep credentials/secrets outside repository and container images.
- Tune Bedrock timeout/retry env vars for latency and resilience.
