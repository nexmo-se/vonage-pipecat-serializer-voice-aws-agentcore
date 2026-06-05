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

![Architecture overview — local dev and production call flows](images/architecture-overview-serializer.png)

**Local dev:** Vonage → ngrok → `app/` FastAPI `/answer` → WebSocket `/ws` → Pipecat → Nova Sonic

**Production:** Vonage → App Runner `answer/` `/answer` → presigned AgentCore WSS URL → `runtime/` AgentCore → Pipecat → Nova Sonic

**Audio-only design:** Uses the Vonage Audio Serializer (WebSocket), not the Video Connector (WebRTC). Recommended for voice-only AI per [official Vonage guidance](https://developer.vonage.com/en/video/guides/vonage-pipecat-serializer-overview).

## Prerequisites

- Docker Desktop — required for local dev (`docker compose`) and building the App Runner image
- **Python 3.12** — required for `aws_sdk_bedrock_runtime` (Nova Sonic). Python 3.11 installs silently but crashes at runtime
- AWS CLI with credentials:
  - `AmazonBedrockFullAccess` + `BedrockAgentCoreFullAccess` (AgentCore Runtime)
  - `AWSAppRunnerFullAccess` + ECR access (App Runner)
- `bedrock-agentcore-starter-toolkit` — install via `pip install bedrock-agentcore-starter-toolkit`
- ngrok with a reserved domain (local dev only)
- Vonage Voice application with a public Answer URL and `private.key` for local dev

## Repository Layout

```text
vonage-pipecat-serializer-voice-aws-agentcore/
├── app/                 # LOCAL DEV — FastAPI app, port 8000, ngrok webhook
├── runtime/             # PRODUCTION — BedrockAgentCoreApp, port 8080, agentcore deploy
├── answer/              # PRODUCTION — /answer handler (App Runner or Lambda Function URL)
├── images/              # Architecture diagrams
├── docker-compose.yml
└── .env.example
```

## Local Dev Setup

```bash
cp .env.example .env
# Fill in VONAGE_APPLICATION_ID, VONAGE_PRIVATE_KEY, AWS_PROFILE, BEDROCK_MODEL_ID
# Place your Vonage private key at ./private.key

docker compose --profile app up --build app
ngrok http --domain=your-reserved-domain.ngrok.app 8000

# Set Vonage Answer URL → https://your-reserved-domain.ngrok.app/answer
```

## Environment Variables

Key variables (see `.env.example` for the full list):

| Variable | Required | Description |
| --- | --- | --- |
| `VONAGE_APPLICATION_ID` | local/tests | Vonage app ID |
| `VONAGE_PRIVATE_KEY` | local/tests | Path to Vonage private key file |
| `AWS_PROFILE` | local | AWS CLI profile for local dev and deploy commands |
| `AWS_REGION` | yes | AWS region (e.g. `us-east-1`) |
| `BEDROCK_MODEL_ID` | yes | `amazon.nova-2-sonic-v1:0` |
| `VONAGE_NUMBER` | prod | Your Vonage virtual number (E.164) |
| `AGENTCORE_RUNTIME_ARN` | prod | AgentCore Runtime ARN from `agentcore deploy` |
| `BEDROCK_INITIAL_USER_MESSAGE` | recommended | Opening greeting — prevents Nova Sonic 532 timeout |
| `BEDROCK_SYSTEM_INSTRUCTION` | recommended | System prompt that shapes agent behavior |

> **Production note:** `.env` is used for local dev. The AgentCore Runtime container uses defaults in `runtime/agent.py` (or runtime env vars if configured). App Runner only needs `AGENTCORE_RUNTIME_ARN`, `VONAGE_NUMBER`, and `AWS_DEFAULT_REGION`.

---

## Production Deployment

Production uses **two AWS resources**:

1. **AgentCore Runtime** (`runtime/`) — hosts the Pipecat + Nova Sonic voice agent
2. **App Runner** (`answer/`) — public `/answer` webhook that returns NCCO with a presigned AgentCore WebSocket URL

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

Edit the defaults in `runtime/agent.py` **before deploying**:

| Variable | Purpose |
| --- | --- |
| `BEDROCK_SYSTEM_INSTRUCTION` | Agent behavior (e.g. nurse triage, support desk) |
| `BEDROCK_INITIAL_USER_MESSAGE` | Opening line spoken when the caller connects |

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

### Step 5 — Deploy the `/answer` webhook to App Runner

App Runner runs `answer/server.py` (FastAPI wrapper around `answer/answer.py`).

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

### Step 6 — Configure Vonage

Set your Vonage application's **Answer URL** to:

```text
https://{service-id}.{region}.awsapprunner.com/answer
```

Verify it returns valid NCCO:

```bash
curl "https://{service-id}.{region}.awsapprunner.com/answer"
```

Expected response shape:

```json
[{"action":"connect","from":"+1...","endpoint":[{"type":"websocket","uri":"wss://bedrock-agentcore..."}]}]
```

Call your Vonage number to test end-to-end.

---

## `/answer` Webhook Options

| Option | Status | Requirement |
| --- | --- | --- |
| **A — App Runner** | Recommended | `AWSAppRunnerFullAccess` + ECR access |
| **B — Lambda Function URL** | Alternative | Lambda execution role + `AuthType: NONE` Function URL |
| **C — ngrok + `answer/server.py`** | Local dev / fallback | No AWS deployment needed |

### Option B — Lambda Function URL

Lambda is simpler and cheaper at low volume, but may be blocked by org-level SCPs on `lambda:InvokeFunctionUrl`.

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

## Production Notes

- Always use **Python 3.12** for AgentCore Runtime — Nova Sonic silently fails on 3.11
- Use `pipecat-ai[aws-nova-sonic,websocket]>=1.3.0` — the `aws-nova-sonic` extra installs `aws_sdk_bedrock_runtime`
- `await websocket.accept()` is required at the top of every `@app.websocket` handler — `BedrockAgentCoreApp` does not auto-accept
- Inside AgentCore Runtime, boto3 uses IMDS credentials automatically — no static keys needed
- Set `BEDROCK_INITIAL_USER_MESSAGE` to prevent Nova Sonic 532 timeout (55s wait for first audio)
- Use `AgentCoreRuntimeClient.generate_presigned_url()` for presigned URLs — raw boto3 generates the wrong URL type
- App Runner only handles `/answer`; the voice agent and greeting live in AgentCore Runtime (`runtime/agent.py`)
