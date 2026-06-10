# vonage-pipecat-serializer-voice-aws-agentcore

Reference implementation of a **production-ready voice AI agent** for live Vonage phone calls using:

- **[Vonage Audio Serializer for Pipecat](https://developer.vonage.com/en/voice/voice-api/guides/vonage-audio-serializer-for-pipecat-overview)** — `VonageFrameSerializer` bridges Vonage Voice WebSocket PCM audio into a Pipecat pipeline (no WebRTC, no separate Audio Connector SDK for phone calls)
- **[AWS Bedrock Nova Sonic](https://aws.amazon.com/bedrock/nova/)** — Speech-to-speech conversational AI (no STT → LLM → TTS chain)
- **[AWS Bedrock AgentCore Runtime](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/what-is-bedrock-agentcore.html)** — Fully managed serverless container hosting the Pipecat pipeline

> **The showcase:** `VonageFrameSerializer` + `FastAPIWebsocketTransport` + Nova Sonic, deployed inside AgentCore Runtime and confirmed working end-to-end with real Vonage phone calls.

## What You'll Build

- An AI agent running inside **AgentCore Runtime** — the entire Pipecat pipeline, one instance per inbound WebSocket
- A public **App Runner** endpoint that handles the Vonage `/answer` webhook and returns a pre-signed AgentCore WebSocket URL
- Real-time spoken AI responses via **Nova Sonic** (speech-to-speech)
- A production stack with no EC2, ECS, EKS, or ALB — just `agentcore deploy` and an App Runner service

## Vonage Audio Serializer vs Video Transport

This repo implements the **Vonage Audio Serializer** path (Part 2 of a two-part series). Use it when you need Voice API phone calls or the simplest path to a working agent. For full video frame processing or lowest WebRTC latency, see [Vonage Video Transport for Pipecat](https://developer.vonage.com/en/video/guides/vonage-pipecat-serializer-overview) (Part 1).

| | [Vonage Audio Serializer](https://developer.vonage.com/en/voice/voice-api/guides/vonage-audio-serializer-for-pipecat-overview) (this repo) | [Vonage Video Transport](https://developer.vonage.com/en/video/guides/vonage-pipecat-serializer-overview) (Part 1) |
| --- | --- | --- |
| Protocol | WebSocket | WebRTC |
| Voice API (phone calls) | Yes | No |
| Video API | Yes — via Audio Connector | Yes |
| Full video frames | Audio only | Audio + Video |
| Status | GA | GA |

## Why This Stack?

| Layer | What it does | Why it matters |
| --- | --- | --- |
| **Vonage Voice API (Call Control)** | Handles incoming calls via NCCO — returns the WebSocket URI | Standard telephony entry point — no SIP or media gateway |
| **Vonage Voice API (Audio WebSocket)** | Streams PCM audio from the live call over WebSocket | Raw 16 kHz PCM delivered directly to your server in real time |
| **Vonage Audio Serializer for Pipecat** | Converts Vonage PCM frames to/from Pipecat's internal format | The bridge between Vonage telephony and the Pipecat AI pipeline |
| **Amazon Nova Sonic** | Speech-to-speech AI — voice in, voice out | Sub-second latency without the STT → LLM → TTS chain |
| **Amazon Bedrock** | Runs Nova Sonic model inference | The model layer — Bedrock answers |
| **Amazon Bedrock AgentCore** | Production runtime for deploying and scaling your agent | AgentCore runs your deployable agent logic — infrastructure, scaling, and WebSocket routing |

> **Bedrock answers. AgentCore runs your agent.** In production, `runtime/agent.py` **is** the AgentCore-hosted service — not a caller of AgentCore.

## Architecture

![Architecture overview — local dev and production call flows](images/architecture-overview-serializer.png)

**Local dev:**

```text
Caller → Vonage Voice API
  ↓ GET /answer → ngrok → app/main.py /answer (NCCO with wss://ngrok/ws)
  ↓ WebSocket → app/agent.py /ws
VonageFrameSerializer → Pipecat Pipeline → Nova Sonic → caller
```

**Production:**

```text
Caller → Vonage Voice API
  ↓ GET /answer → App Runner answer/server.py /answer
    AgentCoreRuntimeClient.generate_presigned_url()
    → NCCO with wss://bedrock-agentcore.../runtimes/{arn}/ws?...
  ↓ WebSocket → AgentCore Runtime runtime/agent.py /ws
    await websocket.accept()  ← required
VonageFrameSerializer → Pipecat Pipeline → Nova Sonic → caller
```

**Audio-only design:** Uses the Vonage Audio Serializer (WebSocket), not the Vonage Video Transport (WebRTC). Recommended for voice-only AI per [official Vonage guidance](https://developer.vonage.com/en/voice/voice-api/guides/vonage-audio-serializer-for-pipecat-overview).

### Local dev vs production

| | Local dev | Production |
| --- | --- | --- |
| `/answer` handler | `app/main.py` via ngrok | App Runner (`answer/`) |
| Agent host | Local Docker container (`app/`) | AgentCore Runtime (`runtime/`) |
| WebSocket URI in NCCO | `wss://your-reserved-domain.ngrok.app/ws` | Pre-signed AgentCore WSS URL |
| AWS credentials | `AWS_PROFILE` / `.env` | IMDS automatic (AgentCore); IAM role (App Runner) |
| Greeting / persona | `.env` | `runtime/agent.py` defaults |

**What never changes:** `VonageFrameSerializer`, the Pipecat pipeline, and Nova Sonic — identical in both environments.

## Prerequisites

- **Vonage API account** with Voice API enabled and a phone number linked to a Voice application
- **AWS account** with Amazon Bedrock access and Nova Sonic (`amazon.nova-2-sonic-v1:0`) enabled in `us-east-1`
- **Python 3.12** — required for **AgentCore Runtime** (`runtime/`). `aws_sdk_bedrock_runtime` is only distributed for Python 3.12+; Python 3.11 installs silently but crashes at runtime. Local `app/` uses Python 3.13 via Docker.
- **Docker Desktop** — required for local dev (`docker compose`) and building the App Runner image
- **ngrok** with a reserved domain (local dev only)
- **AWS CLI** configured (`aws configure --profile your-profile`) with Bedrock access in `us-east-1`
- **`bedrock-agentcore-starter-toolkit`** — `pip install bedrock-agentcore-starter-toolkit`
- Vonage Voice application with a public Answer URL (inbound webhook flow — no Vonage credentials needed on the agent side)

## Repository Layout

```text
vonage-pipecat-serializer-voice-aws-agentcore/
├── app/                 # LOCAL DEV — FastAPI (main.py, agent.py), port 8000, ngrok webhook
├── runtime/             # PRODUCTION — BedrockAgentCoreApp (agent.py), port 8080
│                        #   direct code deploy via agentcore deploy — no Dockerfile
│                        #   .bedrock_agentcore.yaml generated by agentcore configure (gitignored)
├── answer/              # PRODUCTION — /answer handler (App Runner), port 3000
│   ├── answer.py        #   presigned URL + NCCO logic (shared with Lambda option)
│   ├── server.py        #   FastAPI wrapper for App Runner / local ngrok
│   └── Dockerfile       #   python:3.12-slim
├── images/              # Architecture diagrams
├── blog/                # Tutorial draft (blog-post.md)
├── docker-compose.yml
└── .env.example
```

## Quick Start — Local Dev

```bash
git clone https://github.com/nexmo-se/vonage-pipecat-serializer-voice-aws-agentcore.git
cd vonage-pipecat-serializer-voice-aws-agentcore

cp .env.example .env
# Fill in AWS_PROFILE, BEDROCK_MODEL_ID, BEDROCK_INITIAL_USER_MESSAGE (recommended)
# VONAGE_APPLICATION_ID / VONAGE_PRIVATE_KEY are optional — not used by the inbound webhook flow

docker compose --profile app up --build app
ngrok http --domain=your-reserved-domain.ngrok.app 8000

# Set Vonage Answer URL → https://your-reserved-domain.ngrok.app/answer
```

Verify the NCCO:

```bash
curl "https://your-reserved-domain.ngrok.app/answer"
```

Expected response shape:

```json
[
  {
    "action": "connect",
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

> Local `app/main.py` omits the `from` field. Production `answer/answer.py` includes `"from": VONAGE_NUMBER`.

Hang up programmatically (local dev):

```bash
curl -X POST http://localhost:8000/hangup
```

## Environment Variables

Key variables (see `.env.example` for the full list):

| Variable | Required | Description |
| --- | --- | --- |
| `VONAGE_APPLICATION_ID` | optional | Vonage app ID — used by tests, not the inbound webhook flow |
| `VONAGE_PRIVATE_KEY` | optional | Path to Vonage private key — used by tests, not the inbound webhook flow |
| `VONAGE_NUMBER` | prod (`answer/`) | Your Vonage virtual number (E.164) — required in App Runner env vars |
| `AWS_PROFILE` | local | AWS CLI profile for local dev and deploy commands |
| `AWS_REGION` | yes | AWS region (e.g. `us-east-1`) |
| `BEDROCK_MODEL_ID` | yes | `amazon.nova-2-sonic-v1:0` |
| `BEDROCK_INITIAL_USER_MESSAGE` | recommended | Opening greeting — prevents Nova Sonic 532 timeout |
| `BEDROCK_SYSTEM_INSTRUCTION` | recommended | System prompt that shapes agent behavior |
| `AGENTCORE_RUNTIME_ARN` | prod | AgentCore Runtime ARN from `agentcore deploy` |
| `AGENTCORE_AGENT_ARN` | local (optional) | Enables AgentCore bootstrap in `app/agent.py` |
| `NOVA_SESSION_WARN_SECONDS` | optional | Emit renewal warning before session expiry (default: 410) |
| `NOVA_SESSION_LIMIT_SECONDS` | optional | Hard session-age limit (~8 min window, default: 470) |
| `NOVA_SESSION_STOP_ON_LIMIT` | optional | Set `true` to auto-stop pipeline at limit |

> **Production note:** `.env` is for local dev. The AgentCore Runtime container uses defaults in `runtime/agent.py` (or runtime env vars if configured). App Runner only needs `AGENTCORE_RUNTIME_ARN`, `VONAGE_NUMBER`, and `AWS_DEFAULT_REGION`.

> **Note:** The production webhook flow does not require `VONAGE_CALL_ID`. Vonage calls `/answer`, receives the NCCO, then connects media to the WebSocket URI automatically.

## Voice Pipeline

`app/agent.py` (local dev) and `runtime/agent.py` (production) implement the same 3-stage speech-to-speech pipeline — one instance per inbound Vonage WebSocket connection:

```text
transport.input()  →  AWSNovaSonicLLMService  →  transport.output()
```

Key settings:

- **16 kHz PCM16 mono** — recommended default for Nova Sonic (Vonage also supports 8 kHz–24 kHz)
- **`fixed_audio_packet_size=640`** — 20 ms frames at 16 kHz (640 bytes)
- **`VonageFrameSerializer`** — handles all PCM frame conversion between Vonage and Pipecat

| | `app/agent.py` (local) | `runtime/agent.py` (production) |
| --- | --- | --- |
| App wrapper | `FastAPI()` | `BedrockAgentCoreApp()` |
| Port | 8000 | 8080 (AgentCore requirement) |
| `/answer` endpoint | Present in `app/main.py` | Removed — App Runner handles it |
| AWS credentials | `AWS_PROFILE` / `.env` | IMDS automatic — no static keys |
| AgentCore bootstrap | Optional local call | Removed — agent **is** AgentCore |

---

## Production Deployment

Production uses **two AWS resources**:

1. **AgentCore Runtime** (`runtime/`) — hosts the Pipecat + Nova Sonic voice agent
2. **App Runner** (`answer/`) — public `/answer` webhook that returns NCCO with a presigned AgentCore WebSocket URL

**Total AWS resources:** 1 AgentCore Runtime + 1 App Runner service + 1 ECR repository.

### Step 1 — Install the AgentCore CLI

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install bedrock-agentcore-starter-toolkit
```

### Step 2 — Configure AgentCore Runtime

```bash
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
```

### Step 3 — Customize the greeting and persona

Edit the defaults in `runtime/agent.py` **before deploying** (greeting changes require a runtime redeploy, not App Runner). Do **not** put greeting or persona logic in `answer/` — that handler only generates the presigned URL and NCCO:

| Variable | Purpose |
| --- | --- |
| `BEDROCK_SYSTEM_INSTRUCTION` | Agent behavior (e.g. nurse triage, support desk) |
| `BEDROCK_INITIAL_USER_MESSAGE` | Opening line spoken when the caller connects |

Queue `LLMRunFrame()` on `on_client_connected` to trigger the greeting immediately and prevent Nova Sonic 532 timeout.

Example (nurse triage):

```python
# BEDROCK_SYSTEM_INSTRUCTION default in runtime/agent.py
"You are a nurse triage voice assistant. Ask one short question at a time..."

# BEDROCK_INITIAL_USER_MESSAGE default
"Hello, I am your nurse intake assistant. I will ask a few brief triage questions..."
```

### Step 4 — Deploy the voice agent

```bash
cd runtime/

# First deploy
AWS_PROFILE=your-profile agentcore deploy -a your_agent_name

# Redeploy after code changes (e.g. greeting updates)
AWS_PROFILE=your-profile agentcore deploy -a your_agent_name --auto-update-on-conflict
```

Copy the **Runtime ARN** from the deploy output:

```text
arn:aws:bedrock-agentcore:us-east-1:{account-id}:runtime/your_agent_name-{id}
```

Set it as `AGENTCORE_RUNTIME_ARN` in `.env` and in the App Runner environment variables below.

AgentCore Runtime execution role needs `AmazonBedrockFullAccess` + `BedrockAgentCoreFullAccess`.

### Step 5 — Deploy the `/answer` webhook to App Runner

App Runner runs `answer/server.py` (FastAPI wrapper around `answer/answer.py`). It calls `AgentCoreRuntimeClient.generate_presigned_url()` to generate a fresh pre-signed WSS URL per call.

#### 5a. Build and push the container image

```bash
cd answer/

docker build --platform linux/amd64 -t vonage-agentcore-answer .

export AWS_ACCOUNT_ID=123456789012
export AWS_REGION=us-east-1
export AWS_PROFILE=your-profile
export ECR_URI="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/vonage-agentcore-answer"

aws ecr create-repository --repository-name vonage-agentcore-answer  # first time only
aws ecr get-login-password --region "$AWS_REGION" | \
  docker login --username AWS --password-stdin "${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"

docker tag vonage-agentcore-answer:latest "${ECR_URI}:latest"
docker push "${ECR_URI}:latest"
```

#### 5b. Create the App Runner service (first time)

```bash
aws apprunner create-service \
  --service-name vonage-agentcore-answer \
  --source-configuration "{
    \"ImageRepository\": {
      \"ImageIdentifier\": \"${ECR_URI}:latest\",
      \"ImageRepositoryType\": \"ECR\",
      \"ImageConfiguration\": {
        \"Port\": \"3000\",
        \"RuntimeEnvironmentVariables\": {
          \"AGENTCORE_RUNTIME_ARN\": \"arn:aws:bedrock-agentcore:us-east-1:{account-id}:runtime/your_agent_name-{id}\",
          \"VONAGE_NUMBER\": \"+14155551234\",
          \"AWS_DEFAULT_REGION\": \"us-east-1\"
        }
      }
    },
    \"AuthenticationConfiguration\": {
      \"AccessRoleArn\": \"arn:aws:iam::{account-id}:role/your-apprunner-ecr-access-role\"
    }
  }" \
  --instance-configuration "{
    \"InstanceRoleArn\": \"arn:aws:iam::{account-id}:role/your-apprunner-instance-role\"
  }" \
  --region us-east-1
```

**IAM requirements:**

| Role | Trust | Policies |
| --- | --- | --- |
| App Runner instance role | `tasks.apprunner.amazonaws.com` | `AmazonBedrockFullAccess` + `BedrockAgentCoreFullAccess` |
| ECR access role | `build.apprunner.amazonaws.com` | `AWSAppRunnerServicePolicyForECRAccess` |

#### 5c. Redeploy after `answer/` changes

```bash
cd answer/
docker build --platform linux/amd64 -t vonage-agentcore-answer .
docker tag vonage-agentcore-answer:latest "${ECR_URI}:latest"
docker push "${ECR_URI}:latest"

aws apprunner start-deployment \
  --service-arn "arn:aws:apprunner:us-east-1:{account-id}:service/vonage-agentcore-answer/{service-id}" \
  --region us-east-1
```

#### 5d. Update App Runner environment variables

```bash
aws apprunner update-service --service-arn <arn> \
  --source-configuration '{
    "ImageRepository": {
      "ImageConfiguration": {
        "RuntimeEnvironmentVariables": {
          "AGENTCORE_RUNTIME_ARN": "<runtime-arn-from-step-4>",
          "VONAGE_NUMBER": "<your-vonage-number>",
          "AWS_DEFAULT_REGION": "us-east-1"
        }
      }
    }
  }'
```

### Step 6 — Configure Vonage and test

Set your Vonage application's **Answer URL** to:

```text
https://{service-id}.{region}.awsapprunner.com/answer
```

Verify it returns valid NCCO:

```bash
curl "https://{service-id}.{region}.awsapprunner.com/answer"
```

Expected production NCCO:

```json
[
  {
    "action": "connect",
    "from": "+1...",
    "endpoint": [
      {
        "type": "websocket",
        "uri": "wss://bedrock-agentcore.us-east-1.amazonaws.com/runtimes/{arn}/ws?X-Amz-Algorithm=...",
        "content-type": "audio/l16;rate=16000"
      }
    ]
  }
]
```

**Full production call flow:**

1. Caller dials your Vonage number
2. Vonage sends `GET /answer` to App Runner
3. App Runner calls `AgentCoreRuntimeClient.generate_presigned_url()` — fresh pre-signed WSS URL
4. App Runner returns NCCO with pre-signed URL
5. Vonage connects to AgentCore Runtime `/ws` using the pre-signed URL
6. `runtime/agent.py` calls `await websocket.accept()` — `VonageFrameSerializer` initializes
7. Pipecat pipeline starts — Nova Sonic processes speech-to-speech in real time
8. Audio response streams back to caller

> The pre-signed URL expires in 300 seconds, but the WebSocket connection persists for the full call duration once established.

Call your Vonage number to test end-to-end.

---

## `/answer` Webhook Options

| Option | Status | Requirement |
| --- | --- | --- |
| **A — App Runner** | Recommended | `AWSAppRunnerFullAccess` + ECR access |
| **B — Lambda Function URL** | Alternative | Lambda execution role + `AuthType: NONE` Function URL |
| **C — ngrok + `answer/server.py`** | Local dev / fallback | No AWS deployment needed |

### Option B — Lambda Function URL

Lambda is simpler and cheaper at low volume, but may be blocked by org-level SCPs on `lambda:InvokeFunctionUrl`. The pre-signed URL generation logic is identical to App Runner.

```bash
cd answer/

# Package handler + dependencies
mkdir -p package
pip install bedrock-agentcore -t package/
cp answer.py package/
cd package && zip -r ../lambda.zip . && cd ..

aws lambda create-function \
  --function-name vonage-answer \
  --runtime python3.12 \
  --handler answer.handler \
  --zip-file fileb://lambda.zip \
  --role "arn:aws:iam::{account-id}:role/vonage-answer-role" \
  --environment "Variables={AGENTCORE_RUNTIME_ARN=arn:aws:bedrock-agentcore:us-east-1:{account-id}:runtime/your_agent_name-{id},VONAGE_NUMBER=+14155551234,AWS_DEFAULT_REGION=us-east-1}"

aws lambda create-function-url-config \
  --function-name vonage-answer \
  --auth-type NONE

# Set the Function URL as your Vonage Answer URL
```

> **Lambda blocker:** `lambda:InvokeFunctionUrl` may be blocked by an org-level SCP. IAM simulation (`simulate-principal-policy`) returns `allowed` but does not evaluate SCPs — the actual HTTP request returns HTTP 403. App Runner is not subject to this restriction.

### Option C — Local `/answer` with ngrok

Useful for testing the production call flow without deploying App Runner:

```bash
cd answer/
pip install -r requirements.txt

AGENTCORE_RUNTIME_ARN="arn:aws:bedrock-agentcore:..." \
VONAGE_NUMBER="+14155551234" \
AWS_PROFILE=your-profile \
uvicorn server:app --host 0.0.0.0 --port 3000

# In another terminal:
ngrok http 3000

# Set Vonage Answer URL → https://<ngrok-id>.ngrok.io/answer
```

---

## Nova Sonic Session Limit

AWS Nova Sonic has an ~8 minute connection window per session. Both `app/agent.py` and `runtime/agent.py` monitor session age via `NOVA_SESSION_WARN_SECONDS` / `NOVA_SESSION_LIMIT_SECONDS`. Local dev also emits a `session_renewal_recommended` event on the `/events` WebSocket; production runtime logs a renewal warning to CloudWatch.

```bash
NOVA_SESSION_LIMIT_SECONDS=470    # hard limit (~8 min window)
NOVA_SESSION_WARN_SECONDS=410     # emit renewal warning at this age
NOVA_SESSION_STOP_ON_LIMIT=false  # set true to auto-stop at limit
```

## Key Dependencies

```text
# Production runtime (runtime/requirements.txt) — PyPI, Python 3.12
pipecat-ai[aws-nova-sonic,websocket]>=1.3.0
bedrock-agentcore>=0.1.0
structlog>=24.1.0
uvicorn[standard]>=0.29.0

# Answer handler + App Runner container (answer/requirements.txt) — Python 3.12
bedrock-agentcore>=0.1.0
fastapi>=0.110.0
uvicorn[standard]>=0.29.0

# Local dev app (app/requirements.txt) — Python 3.13, Vonage pipecat fork
pipecat-ai[aws,aws-nova-sonic,silero] @ git+https://github.com/Vonage/pipecat.git
```

> **Production:** Use `pipecat-ai` from PyPI — `VonageFrameSerializer` is included in upstream `pipecat-ai>=1.3.0`. No Vonage fork required for `runtime/`.
>
> Both `[aws-nova-sonic]` and `[websocket]` extras are required for the runtime:
> - `[aws-nova-sonic]` → installs `aws_sdk_bedrock_runtime` (Nova Sonic bidirectional streaming) — **Python 3.12+ only**
> - `[websocket]` → installs `fastapi` (required by `FastAPIWebsocketTransport`)
>
> Omitting either extra installs silently but crashes at runtime. All production Dockerfiles use `python:3.12-slim`.

## Critical Findings

These were discovered during production deployment. Skipping any of these will break the deployment.

1. **`await websocket.accept()` is mandatory in AgentCore Runtime** — `BedrockAgentCoreApp` does not auto-accept. Without it, AgentCore closes the connection with error 1008 "write buffer limit exceeded." The same error can also mean imports failed before the pipeline started — verify all packages in `runtime/requirements.txt` install cleanly.

2. **Python 3.12 is required for Nova Sonic** — `aws_sdk_bedrock_runtime` is only distributed for Python 3.12+. Python 3.11 installs silently and crashes with `ModuleNotFoundError`.

3. **Set `BEDROCK_INITIAL_USER_MESSAGE` to prevent Nova Sonic 532 timeout** — Nova Sonic times out with `InternalErrorCode=532` after 55 seconds if no audio arrives. Queue `LLMRunFrame()` on `on_client_connected` to trigger the greeting immediately.

4. **Use `AgentCoreRuntimeClient` for presigned URLs — not raw boto3** — `generate_presigned_url()` produces the correct `wss://` URL. Raw boto3 `invoke_agent_runtime` presign produces an `https://` POST URL that returns HTTP 405 on WebSocket upgrade.

5. **AgentCore Runtime agent IS the AgentCore service** — do not call `invoke_agent_runtime()` from inside the runtime to bootstrap itself. Remove any bootstrap code from `runtime/agent.py`.

## Production Checklist

- [ ] Use Python 3.12 for AgentCore Runtime — Nova Sonic silently fails on 3.11
- [ ] `await websocket.accept()` as first line in `runtime/agent.py` `@app.websocket` handler
- [ ] Set `BEDROCK_INITIAL_USER_MESSAGE` to prevent Nova Sonic 532 timeout
- [ ] Use `AgentCoreRuntimeClient.generate_presigned_url()` — not raw boto3
- [ ] Use IAM roles — never static AWS keys in production
- [ ] Store `VONAGE_NUMBER` and `AGENTCORE_RUNTIME_ARN` in App Runner environment variables
- [ ] Set Vonage Answer URL to App Runner `/answer` before go-live
- [ ] `curl` the `/answer` endpoint and confirm NCCO contains `wss://bedrock-agentcore...` before a real call
- [ ] Tune `NOVA_SESSION_WARN_SECONDS` / `NOVA_SESSION_LIMIT_SECONDS` for calls longer than 8 minutes

## Further Resources

- [Vonage Voice API docs](https://developer.vonage.com/en/voice/voice-api/overview)
- [Vonage Audio Serializer for Pipecat](https://developer.vonage.com/en/voice/voice-api/guides/vonage-audio-serializer-for-pipecat-overview)
- [AWS Nova Sonic docs](https://docs.aws.amazon.com/nova/latest/userguide/what-is-nova.html)
- [AWS Bedrock AgentCore docs](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/what-is-bedrock-agentcore.html)
- [Tutorial draft](blog/blog-post.md) — full walkthrough with code samples
