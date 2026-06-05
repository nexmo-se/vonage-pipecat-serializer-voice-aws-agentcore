# Deploying a Real-Time AI Agent for Voice Calls with Vonage and AWS AgentCore

The Vonage Audio Serializer for Pipecat is designed for audio-only AI use cases across both Vonage Voice API and Video API. It is the simplest path to a working agent and the right choice when you don't need video frame processing. If you need full video frame processing or video avatars, see Part 1 which covers the Vonage Video Connector Pipecat Integration.

Developers can now deploy AI agents directly into live phone calls. Instead of static IVR menus or scripted bots, you can build AI agents that listen, respond naturally, and take real-world actions — all over a standard Vonage phone call.

In this tutorial, you'll deploy an AI agent for voice calls using the Vonage Audio Serializer for Pipecat and AWS Nova Sonic. The Vonage Audio Serializer for Pipecat is Vonage's integration that bridges real-time voice and video sessions into AI pipelines over WebSocket. AWS Nova Sonic is optimized for low-latency conversational voice interactions, eliminating the traditional STT → LLM → TTS chain with a single speech-to-speech model.

This tutorial uses two complementary Vonage components:

- **Vonage Audio Connector Server SDK** — the Python server SDK that manages the WebSocket connection between Vonage and your server
- **Vonage Pipecat Serializer** — the Pipecat plugin that converts audio frames between Vonage's WebSocket PCM format and Pipecat's internal pipeline format

Together they form the Vonage Audio Serializer for Pipecat integration — a GA path for connecting Vonage Voice and Video sessions to Pipecat pipelines over WebSocket.

You'll use:

- **Vonage Voice API** for telephony — incoming phone calls via WebSocket
- **Vonage Audio Connector Server SDK** for WebSocket session management
- **Vonage Pipecat Serializer** for audio frame conversion
- **Vonage Audio Serializer for Pipecat** for AI pipeline orchestration
- **AWS Nova Sonic** for voice AI
- **AWS Bedrock AgentCore** for optional agent setup and tool support

Skip ahead and find the working code for this sample on [GitHub](https://github.com/nexmo-se/vonage-pipecat-serializer-voice-aws-agentcore).

## What You'll Build

By the end of this tutorial, you'll have:

- An AI agent deployed inside **AWS Bedrock AgentCore Runtime** — a fully managed serverless container that runs your Pipecat pipeline
- A public **App Runner** endpoint that handles the Vonage `/answer` webhook and returns a pre-signed AgentCore WebSocket URL
- Real-time spoken AI responses using **AWS Nova Sonic** (speech-to-speech, no STT/TTS chain)
- A production architecture that requires no EC2, no ECS, no ALB — just `agentcore deploy` and an App Runner service

## Prerequisites

Before you begin, make sure you have the following:

- A Vonage API account with Voice API enabled and a phone number linked to a Voice application
- An AWS account with Amazon Bedrock access and Nova Sonic (`amazon.nova-2-sonic-v1:0`) enabled in `us-east-1`
- **Python 3.12 or later** — the `aws_sdk_bedrock_runtime` package (required for Nova Sonic) is only distributed for Python 3.12+. On Python 3.11 it installs silently without it, causing `ModuleNotFoundError` at runtime.
- Docker Desktop — the app runs in Docker for an isolated, reproducible runtime
- ngrok with a reserved domain for a stable Vonage webhook URL during local development
- AWS CLI configured (`aws configure --profile vonage-dev`)
- `bedrock-agentcore-starter-toolkit` CLI (`pip install bedrock-agentcore-starter-toolkit`) for runtime deployment

Don't have a Vonage account yet? [Sign up for free](https://developer.vonage.com). No AWS account? [Create one here](https://aws.amazon.com).

## This Is Part 2 of a Two-Part Series

Part 1 covered the Vonage Video Connector Pipecat Integration — a WebRTC-based path for AI agents that join Vonage Video sessions as native participants.

This post covers the Vonage Audio Serializer for Pipecat — a WebSocket-based path for voice/telephony use cases. The official Vonage docs summarize the relationship between the two integrations:

> Use the Audio Serializer when you need Voice API support or want the simplest path to a working agent. Use the Video Connector Transport when you need full video frame processing or the lowest possible WebRTC latency.

|                         | Audio Serializer (this post) | Video Connector (Part 1) |
| ----------------------- | ---------------------------- | ------------------------ |
| Protocol                | WebSocket                    | WebRTC                   |
| Voice API (phone calls) | ✅ Yes                       | ❌ No                    |
| Video API               | ✅ Yes — via Audio Connector | ✅ Yes                   |
| Full video frames       | ❌ Audio only                | ✅ Audio + Video         |
| Docker required         | ✅ Yes                       | ✅ Yes                   |
| Status                  | ✅ GA                        | Beta                     |

## Why This Stack?

| Layer                   | What it solves                                                                                           |
| ----------------------- | -------------------------------------------------------------------------------------------------------- |
| Vonage Audio Serializer | Bridges phone call audio (WebSocket PCM) into a Pipecat pipeline without WebRTC complexity               |
| Nova Sonic              | Eliminates the STT → LLM → TTS chain — processes voice end-to-end with sub-second latency                |
| AgentCore               | Gives the voice agent real-world capabilities: query a knowledge base, call an API, look up a CRM record |

Without AgentCore, you get a smart conversational assistant limited to its training data. With AgentCore, you get an agent that can do things — answer questions from your own docs, book appointments, check order status — all over a live phone call.

## How Bedrock and AgentCore Work Together

| Service                     | Role                                                                                                                                  |
| --------------------------- | ------------------------------------------------------------------------------------------------------------------------------------- |
| Amazon Bedrock (Nova Sonic) | Runs model inference for live speech-to-speech conversation                                                                           |
| Amazon Bedrock AgentCore    | Managed runtime that hosts deployable agent logic — invoked at session start to prime the agent with context, persona, or tool access |

Short version: Bedrock answers; AgentCore runs deployable agent app logic.

## Architecture Overview

![Architecture Overview](../images/architecture-overview-serializer.png)

_Architecture overview: Vonage Voice API → App Runner /answer → AgentCore Runtime → VonageFrameSerializer → Pipecat pipeline → AWS Nova Sonic._

```
LOCAL DEV
Caller dials Vonage number
  ↓
Vonage Voice API
  ↓ GET /answer → ngrok → FastAPI /answer (returns NCCO with wss://ngrok/ws)
  ↓ Vonage connects WebSocket to /ws
FastAPI /ws  →  VonageFrameSerializer  →  Pipecat  →  Nova Sonic

PRODUCTION
Caller dials Vonage number
  ↓
Vonage Voice API
  ↓ GET /answer → App Runner /answer
    AgentCoreRuntimeClient.generate_presigned_url()
    → returns NCCO with wss://bedrock-agentcore.../runtimes/{arn}/ws?...
  ↓ Vonage connects via pre-signed WebSocket URL
AgentCore Runtime (runtime/agent.py, port 8080)
  ↓ BedrockAgentCoreApp @app.websocket /ws
  ↓ await websocket.accept()  ← required — BedrockAgentCoreApp does not auto-accept
VonageFrameSerializer + FastAPIWebsocketTransport
  ↓
Pipecat Pipeline → AWS Nova Sonic
  ↓
Audio response streams back to caller
```

| Component | Role |
| ----------------------------------- | ---------------------------------------------------------------- |
| Vonage Voice API | Telephony — incoming phone calls via NCCO WebSocket connect |
| App Runner (`answer/server.py`) | Public HTTPS endpoint — handles `/answer`, generates pre-signed AgentCore WSS URL |
| AgentCore Runtime (`runtime/agent.py`) | Managed serverless container — runs the Pipecat pipeline |
| Vonage Pipecat Serializer | Converts Vonage PCM audio frames to/from Pipecat internal format |
| Amazon Nova Sonic | Low-latency speech-to-speech intelligence |

## Step 1 — Clone the Repository

```bash
git clone https://github.com/nexmo-se/vonage-pipecat-serializer-voice-aws-agentcore.git
cd vonage-pipecat-serializer-voice-aws-agentcore
```

The repository layout:

```text
vonage-pipecat-serializer-voice-aws-agentcore/
├── app/                 # LOCAL DEV — FastAPI app (main.py, agent.py), port 8000
├── runtime/             # PRODUCTION — BedrockAgentCoreApp (agent.py), agentcore deploy
├── answer/              # PRODUCTION — /answer handler (App Runner or Lambda Function URL)
├── docker-compose.yml
├── .env.example
└── README.md            # Full deployment guide
```

## Step 2 — Set Up Your Environment

> **Security note:** Always use IAM roles or temporary credentials in production. Never hardcode AWS secrets in your code or commit them to version control.

```bash
cp .env.example .env
```

Open `.env` and fill in your credentials:

```bash
# Vonage Voice API
VONAGE_APPLICATION_ID=your-vonage-application-id
VONAGE_PRIVATE_KEY=private.key
VONAGE_NUMBER=+14155551234
VONAGE_CALL_ID=your-vonage-call-id          # local/tests only

# AWS
AWS_PROFILE=vonage-dev
AWS_REGION=us-east-1
BEDROCK_MODEL_ID=amazon.nova-2-sonic-v1:0
BEDROCK_CONNECT_TIMEOUT_SECONDS=10
BEDROCK_READ_TIMEOUT_SECONDS=60
BEDROCK_MAX_ATTEMPTS=4
BEDROCK_VALIDATE_MODEL_ID=true

# AgentCore
AGENTCORE_AGENT_ARN=arn:aws:bedrock-agentcore:us-east-1:123456789012:runtime/your-runtime-id   # local bootstrap (optional)
AGENTCORE_RUNTIME_ARN=arn:aws:bedrock-agentcore:us-east-1:123456789012:runtime/your-runtime-id  # production /answer webhook

# Nova Sonic session guard
NOVA_SESSION_WARN_SECONDS=410
NOVA_SESSION_LIMIT_SECONDS=470
NOVA_SESSION_STOP_ON_LIMIT=false

# Agent behavior (local dev via .env; production via runtime/agent.py defaults)
BEDROCK_SYSTEM_INSTRUCTION=You are a helpful voice assistant. Respond warmly and briefly.
BEDROCK_INITIAL_USER_MESSAGE=Hello! How can I help you today?
AGENTCORE_BOOTSTRAP_PROMPT=Provide one short greeting plus one helpful follow-up question for a live voice assistant session.

# App
PORT=8000
```

Configure your AWS profile:

```bash
aws configure --profile vonage-dev
export AWS_PROFILE=vonage-dev
aws sts get-caller-identity --profile vonage-dev
```

> **Note:** The production app webhook flow does not require `VONAGE_CALL_ID` at runtime. Vonage calls `/answer`, receives the NCCO, then connects media to `/ws` automatically.

## Step 3 — Build the Vonage Audio Serializer Pipeline

`app/agent.py` (local dev) and `runtime/agent.py` (production) implement the voice pipeline — one instance per inbound Vonage WebSocket connection. The Vonage Pipecat Serializer handles all PCM audio frame conversion between Vonage's WebSocket format and Pipecat's internal pipeline format.

```python
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.serializers.vonage import VonageFrameSerializer
from pipecat.services.aws.nova_sonic.llm import AWSNovaSonicLLMService, Params
from pipecat.transports.websocket.fastapi import (
    FastAPIWebsocketParams,
    FastAPIWebsocketTransport,
)

# Vonage telephony-grade audio framing: 640 bytes = 20ms @ 16kHz PCM16 mono
serializer = VonageFrameSerializer(
    params=VonageFrameSerializer.InputParams(
        vonage_sample_rate=16000,
    )
)

transport = FastAPIWebsocketTransport(
    websocket=websocket,
    params=FastAPIWebsocketParams(
        audio_in_enabled=True,
        audio_out_enabled=True,
        add_wav_header=False,
        fixed_audio_packet_size=640,  # 20ms PCM frame at 16kHz
        serializer=serializer,
        vad_analyzer=SileroVADAnalyzer(),
    ),
)

# AWS Nova Sonic — speech-to-speech AI
nova_sonic = AWSNovaSonicLLMService(
    access_key_id=frozen_credentials.access_key,
    secret_access_key=frozen_credentials.secret_key,
    session_token=frozen_credentials.token,
    region=aws_region,
    model=bedrock_model_id,
    params=Params(
        input_sample_rate=16000,
        input_channel_count=1,
        output_sample_rate=16000,
        output_channel_count=1,
    ),
    system_instruction=system_instruction,
)

# 3-stage speech-to-speech pipeline
pipeline = Pipeline([
    transport.input(),      # Audio in from Vonage phone call
    nova_sonic,             # Speech-to-speech AI processing
    transport.output(),     # Audio out back to caller
])
```

## Step 4 — Deploy to AgentCore Runtime

The `runtime/agent.py` file is your production agent — it runs **inside** AgentCore Runtime as the managed container. It is not a caller of AgentCore; it IS the AgentCore-hosted service.

Key structural differences from `app/agent.py` (local dev):

| | `app/agent.py` (local dev) | `runtime/agent.py` (production) |
|---|---|---|
| App wrapper | `FastAPI()` | `BedrockAgentCoreApp()` |
| Port | 8000 | **8080** (AgentCore requirement) |
| `/answer` endpoint | ✅ Present | ❌ Removed — App Runner handles it |
| AWS credentials | `AWS_PROFILE` / `.env` | **IMDS automatic** — no static keys |
| AgentCore bootstrap | optional call | **removed** — agent IS in AgentCore |

```python
from bedrock_agentcore.runtime import BedrockAgentCoreApp
from starlette.websockets import WebSocket

app = BedrockAgentCoreApp()

@app.websocket
async def ws_handler(websocket: WebSocket, context) -> None:
    # REQUIRED: BedrockAgentCoreApp does not auto-accept WebSocket connections.
    # Without this, AgentCore closes with error 1008 "write buffer limit exceeded".
    await websocket.accept()

    # Build initial context.
    # No AgentCore bootstrap — this agent IS in AgentCore.
    if bedrock_initial_user_message:
        @transport.event_handler("on_client_connected")
        async def on_client_connected(t, client):
            await pipeline_task.queue_frame(LLMContextFrame(context))
            await pipeline_task.queue_frame(LLMRunFrame())
            # Queuing LLMRunFrame() immediately prevents Nova Sonic 532 timeout
            # (55s timeout waiting for audio/speech when no initial message is set)

    # ... VonageFrameSerializer + FastAPIWebsocketTransport + Nova Sonic pipeline

if __name__ == "__main__":
    app.run(port=8080)
```

Customize the greeting and persona in `runtime/agent.py` before deploying — edit the `BEDROCK_SYSTEM_INSTRUCTION` and `BEDROCK_INITIAL_USER_MESSAGE` defaults (e.g. nurse triage, support desk).

Deploy the runtime:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install bedrock-agentcore-starter-toolkit

cd runtime/

# First-time setup — creates .bedrock_agentcore.yaml (gitignored)
agentcore configure \
  -e agent.py \
  -r us-east-1 \
  -n your_agent_name \
  --non-interactive \
  --deployment-type direct_code_deploy \
  --runtime PYTHON_3_12 \
  -rf requirements.txt

# First deploy
AWS_PROFILE=vonage-dev agentcore deploy -a your_agent_name

# Redeploy after code changes (e.g. greeting updates)
AWS_PROFILE=vonage-dev agentcore deploy -a your_agent_name --auto-update-on-conflict
```

Copy the **Runtime ARN** from the deploy output and set it as `AGENTCORE_RUNTIME_ARN` in App Runner environment variables.

> **Important:** Use **Python 3.12** (`PYTHON_3_12`). The `aws_sdk_bedrock_runtime` package is only available for Python 3.12+. Python 3.11 installs silently and crashes at runtime with `ModuleNotFoundError`.

## Step 5 — Make a Test Call

**Local dev (ngrok):** The `/answer` endpoint in `app/main.py` returns an NCCO pointing directly to your ngrok WebSocket:

```json
[
  {
    "action": "connect",
    "from": "VONAGE_NUMBER",
    "endpoint": [
      {
        "type": "websocket",
        "uri": "wss://your-reserved-domain.ngrok.app/ws",
        "content-type": "audio/l16;rate=16000"
      }
    ]
  }
]
```

**Production (App Runner + AgentCore Runtime):** The `/answer` endpoint in `answer/answer.py` (served by App Runner) generates a **fresh pre-signed AgentCore WebSocket URL per call**:

```json
[
  {
    "action": "connect",
    "from": "+14155551234",
    "endpoint": [
      {
        "type": "websocket",
        "uri": "wss://bedrock-agentcore.us-east-1.amazonaws.com/runtimes/arn%3Aaws%3A.../ws?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Credential=...&X-Amz-Expires=300&X-Amz-Signature=...",
        "content-type": "audio/l16;rate=16000"
      }
    ]
  }
]
```

The pre-signed URL is generated by `AgentCoreRuntimeClient.generate_presigned_url()` from the `bedrock-agentcore` SDK. It expires after 300 seconds — Vonage must connect before it expires.

> **Important:** Do NOT use the raw boto3 `bedrock-agentcore` client's `generate_presigned_url('invoke_agent_runtime', ...)`. That generates an HTTPS POST URL which returns HTTP 405 for WebSocket upgrade requests. Use `AgentCoreRuntimeClient` from `bedrock_agentcore.runtime`.

The full production call flow is:

1. Vonage requests `GET /answer` → App Runner endpoint
2. App Runner calls `AgentCoreRuntimeClient.generate_presigned_url()`
3. Returns NCCO with pre-signed `wss://bedrock-agentcore.../ws?...` URL
4. Vonage connects via the pre-signed WebSocket URL to AgentCore Runtime
5. AgentCore routes to `runtime/agent.py` → `await websocket.accept()`
6. `VonageFrameSerializer` + `FastAPIWebsocketTransport` initializes
7. Pipecat pipeline starts; Nova Sonic sends initial greeting
8. Real-time speech-to-speech conversation begins

To hang up programmatically:

```bash
curl -X POST http://localhost:8000/hangup
```

## Nova Sonic Session Limit

AWS Nova Sonic has an ~8 minute connection window per session. The agent monitors session age and emits a `session_renewal_recommended` event before the limit is reached. Key environment variables for tuning:

```bash
NOVA_SESSION_LIMIT_SECONDS=470          # hard limit (~8 min window)
NOVA_SESSION_WARN_SECONDS=410           # emit renewal warning at this age
NOVA_SESSION_STOP_ON_LIMIT=false        # set true to auto-stop at limit
```

## Key Dependencies

```
# Runtime agent (runtime/requirements.txt)
pipecat-ai[aws-nova-sonic,websocket]>=1.3.0
bedrock-agentcore>=0.1.0
uvicorn[standard]>=0.29.0

# Answer handler + App Runner container (answer/requirements.txt)
bedrock-agentcore>=0.1.0
fastapi>=0.110.0
uvicorn[standard]>=0.29.0
```

> **Note:** Use `pipecat-ai` from PyPI directly — `VonageFrameSerializer` is included in upstream `pipecat-ai>=1.3.0`. No Vonage fork required.
>
> Both extras are required for the runtime:
> - `[aws-nova-sonic]` → installs `aws_sdk_bedrock_runtime` (Nova Sonic bidirectional streaming) — **Python 3.12+ only**
> - `[websocket]` → installs `fastapi` (required by `FastAPIWebsocketTransport`)

## Deploying to Production

The production architecture requires two AWS resources: an **AgentCore Runtime** (your Pipecat agent) and an **App Runner service** (your `/answer` webhook). No EC2, no ECS, no ALB.

See the root [README.md](../README.md) for the complete step-by-step deployment guide. Summary:

### Step 1 — Deploy the agent to AgentCore Runtime

Follow **Step 4** in the README (`agentcore configure` + `agentcore deploy`). AgentCore Runtime handles container lifecycle, auto-scaling, IMDS credentials for boto3, and WebSocket routing to your `@app.websocket` handler.

**IAM execution role** needs `AmazonBedrockFullAccess` + `BedrockAgentCoreFullAccess`.

### Step 2 — Build and deploy the App Runner answer service

App Runner provides a public HTTPS endpoint that Vonage calls for `/answer`. It runs `answer/server.py` (a FastAPI wrapper around `answer/answer.py`):

```bash
cd answer/
docker build --platform linux/amd64 -t vonage-agentcore-answer .

export AWS_ACCOUNT_ID=123456789012
export AWS_REGION=us-east-1
export ECR_URI="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/vonage-agentcore-answer"

aws ecr create-repository --repository-name vonage-agentcore-answer  # first time only
aws ecr get-login-password --region "$AWS_REGION" | \
  docker login --username AWS --password-stdin "${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"

docker tag vonage-agentcore-answer:latest "${ECR_URI}:latest"
docker push "${ECR_URI}:latest"

# Create App Runner service (first time)
aws apprunner create-service \
  --service-name vonage-agentcore-answer \
  --source-configuration "{
    \"ImageRepository\": {
      \"ImageIdentifier\": \"${ECR_URI}:latest\",
      \"ImageRepositoryType\": \"ECR\",
      \"ImageConfiguration\": {
        \"Port\": \"3000\",
        \"RuntimeEnvironmentVariables\": {
          \"AGENTCORE_RUNTIME_ARN\": \"<runtime-arn-from-step-1>\",
          \"VONAGE_NUMBER\": \"<your-vonage-number>\",
          \"AWS_DEFAULT_REGION\": \"us-east-1\"
        }
      }
    },
    \"AuthenticationConfiguration\": {
      \"AccessRoleArn\": \"arn:aws:iam::${AWS_ACCOUNT_ID}:role/your-apprunner-ecr-access-role\"
    }
  }" \
  --instance-configuration "{
    \"InstanceRoleArn\": \"arn:aws:iam::${AWS_ACCOUNT_ID}:role/your-apprunner-instance-role\"
  }" \
  --region us-east-1

# Redeploy after answer/ changes
aws apprunner start-deployment \
  --service-arn "arn:aws:apprunner:us-east-1:{account-id}:service/vonage-agentcore-answer/{service-id}" \
  --region us-east-1
```

**App Runner IAM setup:**
- **Instance role** (trust: `tasks.apprunner.amazonaws.com`): `AmazonBedrockFullAccess` + `BedrockAgentCoreFullAccess`
- **ECR access role** (trust: `build.apprunner.amazonaws.com`): `AWSAppRunnerServicePolicyForECRAccess`

> **Alternative:** Lambda Function URL can replace App Runner in accounts without `lambda:InvokeFunctionUrl` SCP restrictions. See README Option B.

### Step 3 — Set Vonage Answer URL

In your Vonage Dashboard → Applications → your app, set the **Answer URL** to:

```text
https://{service-id}.{region}.awsapprunner.com/answer
```

Verify it returns a valid NCCO:

```bash
curl "https://{service-id}.{region}.awsapprunner.com/answer"
```

Expected response shape:

```json
[{"action":"connect","from":"+1...","endpoint":[{"type":"websocket","uri":"wss://bedrock-agentcore..."}]}]
```

**Total AWS resources:** 1 AgentCore Runtime + 1 App Runner service + 1 ECR repository.

## Critical Findings

These were discovered during production deployment. Skipping any of these will break the deployment.

**1. `await websocket.accept()` is mandatory in AgentCore Runtime**

`BedrockAgentCoreApp` does NOT call `websocket.accept()` before routing to your handler. Without it, AgentCore enforces a write-buffer limit and closes the connection with error 1008 "write buffer limit exceeded." Always add this as the first line of your `@app.websocket` handler.

**2. Python 3.12 is required for Nova Sonic**

The `aws_sdk_bedrock_runtime` package (required for Nova Sonic bidirectional streaming) is only distributed for Python 3.12+. Selecting Python 3.11 during `agentcore configure` installs everything silently but crashes at runtime with `ModuleNotFoundError: No module named 'aws_sdk_bedrock_runtime'`.

**3. Use `BEDROCK_INITIAL_USER_MESSAGE` to prevent Nova Sonic 532 timeout**

Nova Sonic times out with `InternalErrorCode=532` after 55 seconds if no audio or initial message arrives. Set `BEDROCK_INITIAL_USER_MESSAGE` so an `LLMRunFrame` is queued on `on_client_connected` — this triggers the greeting immediately and bypasses the VAD-triggered speech requirement.

**4. Use `AgentCoreRuntimeClient` for presigned URLs — not raw boto3**

`AgentCoreRuntimeClient.generate_presigned_url()` from `bedrock_agentcore.runtime` produces the correct `wss://` WebSocket URL. Raw boto3's `generate_presigned_url('invoke_agent_runtime', ...)` produces an `https://` POST URL that returns HTTP 405 on WebSocket upgrade.

**5. AgentCore Runtime agent IS the AgentCore service — no bootstrap needed**

When deploying to AgentCore Runtime, your agent is the hosted runtime. Do not call `invoke_agent_runtime()` from inside the runtime to bootstrap itself. Remove any AgentCore bootstrap code from `runtime/agent.py` — it IS AgentCore.

## Production Checklist

- Use Python 3.12 for AgentCore Runtime — Nova Sonic silently fails on 3.11
- Use IAM roles — never static AWS keys in production (IMDS provides credentials automatically inside AgentCore Runtime)
- Store secrets (Vonage number, runtime ARN) in App Runner environment variables or AWS Secrets Manager
- Enable CloudWatch metrics and CloudTrail auditing
- Set `NOVA_SESSION_WARN_SECONDS` and implement session renewal for calls longer than 8 minutes
- Configure health checks on `GET /` for App Runner
- Set Vonage Answer URL to your App Runner domain before go-live
- Verify the `/answer` endpoint returns valid NCCO via `curl` before testing a real call

## Conclusion

You have deployed a real-time AI voice agent using the Vonage Audio Serializer for Pipecat and AWS Nova Sonic — running fully inside **AWS Bedrock AgentCore Runtime** with a public **App Runner** webhook endpoint. No EC2, no ECS, no load balancers. The complete production stack is two AWS services: one `agentcore deploy` and one App Runner container.

The `VonageFrameSerializer` + `FastAPIWebsocketTransport` + `BedrockAgentCoreApp` combination is confirmed working end-to-end with real Vonage phone calls. The five critical findings in this post — `await websocket.accept()`, Python 3.12, `BEDROCK_INITIAL_USER_MESSAGE`, the correct presigned URL API, and removing the AgentCore bootstrap — are the difference between a deployment that works and one that fails silently.

Together with Part 1 (Vonage Video Connector Pipecat Integration), you now have two complementary paths for deploying AI agents on Vonage:

- **Audio Serializer** — voice/telephony-first, WebSocket, GA, broadest coverage across Voice and Video
- **Video Connector** — video session-native, WebRTC, lowest latency, full video frames

We always welcome community involvement. Please feel free to join us on GitHub and the Vonage Community Slack.

## Further Resources

- [Vonage Voice API docs](https://developer.vonage.com/en/voice/voice-api/overview)
- [Vonage Audio Serializer for Pipecat](https://developer.vonage.com/en/voice/voice-api/guides/vonage-audio-serializer-for-pipecat-overview)
- [Vonage Audio Serializer for Pipecat docs](https://developer.vonage.com/en/voice/voice-api/guides/vonage-pipecat-serializer-overview)
- [AWS Nova Sonic docs](https://docs.aws.amazon.com/nova/latest/userguide/what-is-nova.html)
- [AWS Bedrock AgentCore docs](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/what-is-bedrock-agentcore.html)
- [GitHub — vonage-pipecat-serializer-voice-aws-agentcore](https://github.com/nexmo-se/vonage-pipecat-serializer-voice-aws-agentcore)
