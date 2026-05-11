# app

## Overview and architecture

`app/` hosts the FastAPI runtime for the Vonage Audio Serializer + voice agent flow.

This is a production-ready voice agent server that:

- Accepts incoming Vonage Voice calls and establishes WebSocket connection via Vonage Audio Serializer Transport
- Routes media through a Pipecat processing pipeline for AI-powered speech processing
- Uses AWS Bedrock Nova Sonic as the conversational LLM (speech-to-speech)
- Optionally bootstraps agent behavior via AWS Bedrock AgentCore

### Request flow:

```
POST /join (WebSocket upgrade)
  ↓
Vonage Audio Serializer Transport connects
  ↓
Pipecat Pipeline Initialized
  ↓
Audio frames flow: Vonage → Serializer → Pipeline → Bedrock → Response → Serializer → Vonage
  ↓
POST /leave (cleanup)
```

### Components:

- **`voice_serializer_bridge.py`** — Compatibility layer for Vonage Audio Serializer Transport imports
- **`agent.py`** — VonageSerializerVoiceAgent class managing pipeline lifecycle, event handling, and graceful shutdown
- **`main.py`** — FastAPI endpoints for `/join`, `/leave`, `/status`, `/ws` (WebSocket), and lifespan management

## Prerequisites and setup

1. Complete root `.env` setup (Vonage credentials, AWS credentials)
2. Valid `VONAGE_CALL_ID` (from test C1 or manual session creation)
3. AWS Bedrock access with Nova Sonic model enabled
4. Python 3.13+ or Docker

```bash
cd app
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Environment variables

Uses root `.env` values:

- `VONAGE_APPLICATION_ID` — Your Vonage app ID
- `VONAGE_PRIVATE_KEY` — Path to private key or key content
- `VONAGE_CALL_ID` — Voice session ID to join
- `AWS_REGION` — AWS region for Bedrock (e.g., `us-east-1`)
- `BEDROCK_MODEL_ID` — Bedrock model ARN (e.g., Nova Sonic)
- `AGENTCORE_AGENT_ARN` — Optional; enables AgentCore bootstrap
- `PORT` — Server port (default: 8000)

## Run instructions

### Native

```bash
cd app
uvicorn main:app --host 0.0.0.0 --port 8000
```

### Docker

```bash
cd ..
docker compose --profile app up --build app
```

## Test instructions

Quick runtime checks:

```bash
curl http://localhost:8000/
curl http://localhost:8000/status
```

## Validation steps

```bash
curl -X POST http://localhost:8000/join -H "Content-Type: application/json" -d '{"call_id":"'$VONAGE_CALL_ID'"}'
curl -X POST http://localhost:8000/leave
```

Expected:

- `/status` shows `running: true` after join
- WebSocket `/ws` emits call/media lifecycle events

## Production notes

- Deploy on Linux-based hosts/containers.
- Use managed secrets and short-lived credentials.
- Monitor Bedrock latency, retries, and call-duration renewal events.
