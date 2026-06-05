# vonage-pipecat-serializer-voice-aws-agentcore

Reference implementation of a **production-ready voice AI agent** combining:

- **Vonage Audio Serializer for Pipecat** — WebSocket transport for real-time phone call audio
- **AWS Bedrock Nova Sonic** — Speech-to-speech conversational AI (no transcription needed)
- **AWS Bedrock AgentCore Runtime** — Fully managed serverless container hosting the Pipecat pipeline

> **The showcase:** This repo demonstrates how to deploy a Vonage Voice API agent inside AWS Bedrock AgentCore Runtime — `VonageFrameSerializer` + `FastAPIWebsocketTransport` + Nova Sonic, confirmed working end-to-end with a real phone call.

## Why This Stack?

| Layer | What it solves |
| --- | --- |
| **Vonage Audio Serializer** | Bridges phone call audio (WebSocket PCM) into a Pipecat pipeline without WebRTC complexity |
| **Nova Sonic** | Eliminates the STT → LLM → TTS chain — processes voice end-to-end with sub-second latency |
| **AgentCore Runtime** | Fully managed serverless container for the Pipecat agent — no EC2, no ECS, no ALB |

## Architecture

```text
LOCAL DEV
Caller → Vonage Voice API → ngrok → FastAPI /answer
  → NCCO with wss://ngrok/ws
  → Vonage connects WebSocket → VonageFrameSerializer → Pipecat → Nova Sonic

PRODUCTION
Caller → Vonage Voice API → App Runner /answer
  → AgentCoreRuntimeClient.generate_presigned_url()
  → NCCO with wss://bedrock-agentcore.../runtimes/{arn}/ws?...
  → Vonage connects via presigned URL → AgentCore Runtime
  → BedrockAgentCoreApp /ws → VonageFrameSerializer → Pipecat → Nova Sonic
```

**Audio-only design:** Uses the Vonage Audio Serializer (WebSocket), not the Video Connector (WebRTC). Recommended for voice-only AI per [official Vonage guidance](https://developer.vonage.com/en/video/guides/vonage-pipecat-serializer-overview).

See [ARCHITECTURE.md](./ARCHITECTURE.md) for the full technical architecture, deployment steps, and critical findings.

## Prerequisites

- Docker Desktop — required for local dev (`docker compose`) and building the App Runner image. Not required for `agentcore deploy`.
- **Python 3.12** — required for `aws_sdk_bedrock_runtime` (Nova Sonic). Python 3.11 installs silently but crashes at runtime.
- AWS credentials with `AmazonBedrockFullAccess` + `BedrockAgentCoreFullAccess`
- ngrok with a reserved domain (local dev only)
- Vonage Voice application with a public Answer URL

## Repository Layout

```
vonage-pipecat-serializer-voice-aws-agentcore/
├── app/           # LOCAL DEV — FastAPI app, port 8000, ngrok webhook
├── runtime/       # PRODUCTION — BedrockAgentCoreApp, port 8080, agentcore deploy
├── lambda/        # PRODUCTION — /answer handler + App Runner container
├── tests/         # Component validation (Vonage, Bedrock, serializer)
├── tests2/        # AgentCore-specific validation (c5–c8)
├── docker-compose.yml
└── .env.example
```

## Local Dev Setup

```bash
cp .env.example .env
# fill in VONAGE_APPLICATION_ID, VONAGE_PRIVATE_KEY, AWS_PROFILE, BEDROCK_MODEL_ID

docker compose --profile app up --build app
ngrok http --domain=your-reserved-domain.ngrok.app 8000
# Set Vonage Answer URL → https://your-reserved-domain.ngrok.app/answer
```

## Environment Variables

Key variables (see `.env.example` for full list):

| Variable | Required | Description |
|---|---|---|
| `VONAGE_APPLICATION_ID` | ✅ | Vonage app ID |
| `VONAGE_PRIVATE_KEY` | ✅ | Path to Vonage private key file |
| `AWS_PROFILE` | ✅ (local) | AWS CLI profile for local dev |
| `AWS_REGION` | ✅ | AWS region (us-east-1) |
| `BEDROCK_MODEL_ID` | ✅ | `amazon.nova-2-sonic-v1:0` |
| `VONAGE_NUMBER` | ✅ (prod) | Your Vonage virtual number (E.164) |
| `AGENTCORE_RUNTIME_ARN` | ✅ (prod) | AgentCore Runtime ARN from `agentcore deploy` |
| `BEDROCK_INITIAL_USER_MESSAGE` | recommended | Initial greeting — prevents Nova Sonic 532 timeout |

## Production Deployment

Production requires two AWS resources: an AgentCore Runtime (Pipecat agent) and an App Runner service (`/answer` webhook). See [ARCHITECTURE.md](./ARCHITECTURE.md) for full deployment commands.

```bash
# 1. Deploy agent to AgentCore Runtime
cd runtime/
agentcore deploy   # select Python 3.12

# 2. Deploy /answer webhook to App Runner
cd lambda/
docker build --platform linux/amd64 -t vonage-agentcore-answer .
# push to ECR, create App Runner service
# → set ServiceUrl as Vonage Answer URL in dashboard
```

## `/answer` Webhook Options

| Option | Status | Requirement |
|---|---|---|
| **App Runner** ✅ Recommended | Works in all accounts | `AWSAppRunnerFullAccess` + ECR access |
| Lambda Function URL | Blocked in accounts with `lambda:InvokeFunctionUrl` SCP | Requires org-level SCP exception if blocked |
| ngrok + `lambda/server.py` | Local dev / fallback | No AWS deployment needed |

> **Lambda blocker:** `lambda:InvokeFunctionUrl` may be blocked by an org-level SCP. IAM simulation (`simulate-principal-policy`) returns `allowed` but does not evaluate SCPs — the actual HTTP request returns 403. App Runner is not subject to this restriction and is the recommended production path.

## Tests

### `tests/` — component validation
Staged tests (C1–C4b) validating Vonage credentials, audio serializer, Pipecat, and Bedrock. Run sequentially. These validate the local dev stack (`app/`), not the production AgentCore Runtime path.

### `tests2/` — AgentCore production path validation
End-to-end validation of the production architecture:

| Test | What it validates | Status |
|---|---|---|
| c5 | Upstream `aws-agentcore-websocket` example — reference for `BedrockAgentCoreApp` | ✅ Reference |
| c6 | `VonageFrameSerializer` + `FastAPIWebsocketTransport` inside AgentCore Runtime | ✅ PASSED |
| c7 | `lambda/answer.py` generates valid NCCO with presigned AgentCore WSS URL | ✅ PASSED |
| c8 | WebSocket probe → AgentCore Runtime → Nova Sonic returns audio | ✅ PASSED |

## Production Notes

- Always use Python 3.12 for AgentCore Runtime — Nova Sonic silently fails on 3.11
- `await websocket.accept()` is required at the top of every `@app.websocket` handler — `BedrockAgentCoreApp` does not auto-accept
- Inside AgentCore Runtime, boto3 uses IMDS credentials automatically — no static keys needed
- Set `BEDROCK_INITIAL_USER_MESSAGE` to prevent Nova Sonic 532 timeout (55s wait for first audio)
- Use `AgentCoreRuntimeClient.generate_presigned_url()` for presigned URLs — raw boto3 generates the wrong URL type
