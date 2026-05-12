# app

## Overview and architecture

`app/` is the production FastAPI server for the Vonage Voice API + Pipecat + AWS Bedrock pipeline.

This server:

- Handles inbound Vonage Voice calls via a Vonage Answer URL webhook (`GET /answer`)
- Accepts Vonage's WebSocket audio stream on `WS /ws` using `FastAPIWebsocketTransport` + `VonageFrameSerializer`
- Routes audio through a 3-stage Pipecat pipeline: transport → Nova Sonic → transport
- Uses AWS Bedrock Nova Sonic for real-time speech-to-speech AI
- Optionally bootstraps the agent context via AWS Bedrock AgentCore before the call starts

### Request flow

```
Phone call arrives at Vonage
  ↓
GET /answer  →  NCCO: connect WebSocket to wss://<host>/ws
  ↓
WS /ws  ←  Vonage connects with PCM 16kHz audio
  ↓
FastAPIWebsocketTransport + VonageFrameSerializer
  ↓
Pipecat Pipeline: transport.input() → AWSNovaSonicLLMService → transport.output()
  ↓
AWS Bedrock Nova Sonic  ←→  (optional) AgentCore bootstrap
  ↓
Response audio back to caller
```

### Components

- **`agent.py`** — `VonageSerializerVoiceAgent` class: pipeline lifecycle, AgentCore bootstrap, session monitoring
- **`main.py`** — FastAPI: `/answer` webhook, `/ws` Vonage audio, `/events` stream, `/status`, `/hangup`
- **`voice_serializer_bridge.py`** — Retained for reference; not used by the current agent

### API endpoints

| Method | Path      | Description                               |
| ------ | --------- | ----------------------------------------- |
| `GET`  | `/`       | Health check                              |
| `GET`  | `/status` | Call status and event counts              |
| `GET`  | `/answer` | **Vonage webhook** — returns NCCO         |
| `WS`   | `/ws`     | **Vonage audio WebSocket** — one per call |
| `POST` | `/hangup` | Cancel the active call                    |
| `WS`   | `/events` | Real-time event stream for monitoring     |

## Prerequisites and setup

1. Complete root `.env` setup (Vonage credentials, AWS credentials)
2. Vonage application with Answer URL pointing to `https://<your-host>/answer`
3. AWS Bedrock access with Nova Sonic model enabled in `us-east-1`
4. Docker

## Environment variables

Uses root `.env` values:

| Variable                     | Required | Description                                                |
| ---------------------------- | -------- | ---------------------------------------------------------- |
| `AWS_REGION`                 | Yes      | AWS region (e.g., `us-east-1`)                             |
| `BEDROCK_MODEL_ID`           | No       | Defaults to `amazon.nova-2-sonic-v1:0`                     |
| `AWS_PROFILE`                | No       | AWS named profile (falls back to env/instance credentials) |
| `AGENTCORE_AGENT_ARN`        | No       | Enables AgentCore bootstrap when set                       |
| `AGENTCORE_BOOTSTRAP_PROMPT` | No       | Prompt sent to AgentCore before call starts                |
| `BEDROCK_SYSTEM_INSTRUCTION` | No       | System prompt for Nova Sonic                               |
| `PORT`                       | No       | Server port (default: `8000`)                              |

> **Note:** `VONAGE_APPLICATION_ID`, `VONAGE_PRIVATE_KEY`, and `VONAGE_CALL_ID` are not required — the Voice API webhook approach does not need credentials on the agent side. Vonage connects to you.

## Run instructions

### Docker (recommended)

```bash
docker compose --profile app up --build
```

The docker-compose service mounts `~/.aws` and `./private.key` automatically.

### Expose publicly (ngrok)

```bash
# Expose the Docker app service on localhost:8000
ngrok http 8000
```

Set your Vonage application's **Answer URL** to:

```
https://<ngrok-subdomain>.ngrok.app/answer
```

Then make a test call to your Vonage number.

## Verification

```bash
# Health check
curl http://localhost:8000/

# Current call status
curl http://localhost:8000/status

# Test the NCCO webhook directly (simulates Vonage calling your answer URL)
curl -H "Host: yourdomain.ngrok.app" https://yourdomain.ngrok.app/answer
```

Expected NCCO response:

```json
[
  {
    "action": "connect",
    "endpoint": [
      {
        "type": "websocket",
        "uri": "wss://yourdomain.ngrok.app/ws",
        "content-type": "audio/l16;rate=16000"
      }
    ]
  }
]
```

## Key implementation notes

**Why `fixed_audio_packet_size=640`?**  
Vonage sends 20ms PCM frames at 16kHz (16-bit mono). That's 16000 × 0.020 × 2 = 640 bytes. The transport must match this exactly.

**Why no text aggregators in the pipeline?**  
Nova Sonic operates speech-to-speech. Adding `LLMContextAggregatorPair` would wait for text transcription that never completes. The pipeline is intentionally 3 stages only.

**Why push `LLMContextFrame` on connect?**  
Nova Sonic's Bedrock stream must be opened before audio arrives. The `on_client_connected` event handler queues the frame immediately when Vonage connects, ensuring the stream is ready.

**AgentCore bootstrap:**  
When `AGENTCORE_AGENT_ARN` is set, the agent calls AgentCore _before_ accepting the WebSocket. The response shapes the initial LLM context (e.g., greeting style, session metadata) before the caller hears anything.

## Production notes

- Deploy on Linux-based hosts or containers (Docker image uses `python:3.13-slim`)
- Use IAM instance roles or managed secrets instead of static AWS credentials
- Monitor the `/events` WebSocket for `session_renewal_recommended` — Nova Sonic has an ~8 min session limit
- Nova Sonic connection: `us-east-1` only (as of writing)
