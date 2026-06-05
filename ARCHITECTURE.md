# Production Architecture: App Runner + AgentCore Runtime

> **Internal document — not the public README.**
> This captures the production architecture. Confirmed findings are marked ✅. Untested steps are marked ⚠️ pending.

---

## What Is Confirmed vs Planned

| Item | Status | Source |
|---|---|---|
| `VonageFrameSerializer + FastAPIWebsocketTransport` runs inside AgentCore Runtime | ✅ Confirmed | c6 — WebSocket probe connected, PCM frames processed |
| `BedrockAgentCoreApp` exposes `WebSocketRoute("/ws", ...)` on port 8080 | ✅ Confirmed | c6 + SDK source |
| `pipecat-ai>=1.3.0` includes `VonageFrameSerializer` (no Vonage fork needed) | ✅ Confirmed | PyPI + c6 deploy |
| `AgentCoreRuntimeClient.generate_presigned_url()` generates `wss://.../runtimes/{arn}/ws` | ✅ Confirmed | c6 probe used this API successfully |
| `await websocket.accept()` required before `FastAPIWebsocketTransport` | ✅ Confirmed | c6 — omitting it caused immediate disconnect |
| App Runner `/answer` returns valid NCCO with presigned WSS URL | ✅ Confirmed | App Runner `GET /answer` returns correct NCCO — verified via `curl` |
| Vonage connects to AgentCore Runtime via presigned URL | ✅ Confirmed | Real Vonage call — end-to-end tested |
| Full call flow: audio in → Nova Sonic → audio out | ✅ Confirmed | Real Vonage call to AgentCore Runtime — call connected and agent responded |

---

## Full Architecture

```
LOCAL DEV (unchanged):
┌─────────────────────────────────────────────────────────────┐
│  Vonage Voice API                                           │
│    ↓ GET /answer                                            │
│  ngrok → FastAPI /answer  (app/agent.py  port 8000)         │
│    ↓ returns NCCO with wss://ngrok/ws                       │
│  Vonage connects to FastAPI /ws                             │
│    ↓                                                        │
│  VonageFrameSerializer + FastAPIWebsocketTransport          │
│    ↓                                                        │
│  Pipecat Pipeline → AWS Nova Sonic                          │
└─────────────────────────────────────────────────────────────┘

PRODUCTION (✅ fully confirmed — real Vonage call tested end-to-end):
┌─────────────────────────────────────────────────────────────┐
│  Vonage Voice API                                           │
│    ↓ GET /answer                                            │
│  App Runner  (lambda/answer.py via lambda/server.py)        │
│    https://shs62gbuks.us-east-1.awsapprunner.com/answer     │
│    ↓ AgentCoreRuntimeClient.generate_presigned_url()        │
│    ↓ returns NCCO with pre-signed AgentCore WSS URL         │
│  Vonage connects to AgentCore /ws  ← ✅ confirmed           │
│    ↓                                                        │
│  AgentCore Runtime Container  (runtime/agent.py  port 8080) │
│    ↓ BedrockAgentCoreApp @app.websocket /ws  ← ✅ confirmed  │
│  VonageFrameSerializer + FastAPIWebsocketTransport          │
│    ↓                                                        │
│  Pipecat Pipeline → AWS Nova Sonic  ← ✅ confirmed          │
└─────────────────────────────────────────────────────────────┘
```

---

## Component 1 — `/answer` Webhook

**What it does:**
- Receives Vonage `GET /answer` webhook
- Generates a fresh pre-signed AgentCore WSS URL per call via `AgentCoreRuntimeClient`
- Returns NCCO to Vonage

### Option A — App Runner ✅ Recommended

App Runner provides a public HTTPS auto-generated endpoint with no infrastructure to manage.

**Why recommended:**
- Auto-generated public HTTPS URL: `https://{id}.{region}.awsapprunner.com`
- Not subject to `lambda:InvokeFunctionUrl` SCP restrictions
- Fully managed — no servers, no nginx, no ALB
- Runs the same `lambda/answer.py` logic via `lambda/server.py` (FastAPI wrapper)

**IAM requirements:**
- Instance role (trust: `tasks.apprunner.amazonaws.com`): `AmazonBedrockFullAccess` + `BedrockAgentCoreFullAccess`
- ECR access role (trust: `build.apprunner.amazonaws.com`): `AWSAppRunnerServicePolicyForECRAccess`

**Deployed endpoint (confirmed working):**
```
https://shs62gbuks.us-east-1.awsapprunner.com/answer
```

### Option B — Lambda Function URL

Lambda Function URL is simpler and cheaper (~$0/month at low volume vs App Runner's minimum ~$5/month).

**Requirements:**
- Lambda execution role: `AmazonBedrockFullAccess` + `BedrockAgentCoreFullAccess`
- Function URL `AuthType: NONE` + resource policy `Principal: *`
- **No org-level SCP blocking `lambda:InvokeFunctionUrl`**

**Known blocker:** Org-level SCPs can deny `lambda:InvokeFunctionUrl` for public callers even when IAM policies allow it. `aws iam simulate-principal-policy` returns `allowed` but **does not evaluate SCPs** — the actual HTTP request returns HTTP 403 `AccessDeniedException`. If your account is under an AWS Organization, verify the SCP before choosing this option.

Deploy:
```bash
cd lambda/
zip lambda.zip answer.py
aws lambda create-function \
    --function-name vonage-answer \
    --runtime python3.12 \
    --handler answer.handler \
    --zip-file fileb://lambda.zip \
    --role arn:aws:iam::{account}:role/vonage-answer-role \
    --environment Variables="{
        AGENTCORE_RUNTIME_ARN={runtime-arn},
        VONAGE_NUMBER={your-vonage-number},
        AWS_DEFAULT_REGION=us-east-1
    }"

aws lambda create-function-url-config --function-name vonage-answer --auth-type NONE
# → set Function URL as Vonage Answer URL
```

### Option C — Local dev with ngrok

For local development and as a fallback when neither Lambda nor App Runner is available:

```bash
cd lambda/
pip install -r requirements.txt
AGENTCORE_RUNTIME_ARN="..." VONAGE_NUMBER="+1..." AWS_PROFILE=vonage-dev \
    uvicorn server:app --host 0.0.0.0 --port 3000
# ngrok http 3000 → set ngrok URL as Vonage Answer URL
```

### `lambda/answer.py`

```python
import boto3
import uuid
import json
import os
from bedrock_agentcore.runtime import AgentCoreRuntimeClient

def handler(event, context):
    if event.get("requestContext", {}).get("http", {}).get("method") != "GET":
        return {"statusCode": 405, "body": "Method Not Allowed"}

    runtime_arn = os.environ["AGENTCORE_RUNTIME_ARN"]
    session_id = str(uuid.uuid4())

    # AgentCoreRuntimeClient generates wss://.../runtimes/{arn}/ws
    client = AgentCoreRuntimeClient(region=os.environ.get("AWS_DEFAULT_REGION", "us-east-1"))
    presigned_url = client.generate_presigned_url(runtime_arn, session_id=session_id)

    ncco = [{
        "action": "connect",
        "from": os.environ["VONAGE_NUMBER"],
        "endpoint": [{
            "type": "websocket",
            "uri": presigned_url,
            "content-type": "audio/l16;rate=16000"
        }]
    }]
    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(ncco)
    }
```

> **API note:** Use `AgentCoreRuntimeClient.generate_presigned_url()` from the `bedrock-agentcore` SDK.
> This generates `wss://bedrock-agentcore.{region}.amazonaws.com/runtimes/{arn}/ws?...` — the correct WebSocket path.
> The raw boto3 `bedrock-agentcore` client's `generate_presigned_url('invoke_agent_runtime', ...)` generates an HTTPS POST URL that returns HTTP 405 for WebSocket upgrades.

### `lambda/server.py` — FastAPI wrapper (used by App Runner and local dev)

App Runner runs this wrapper, which delegates to `answer.handler`:

```python
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import answer as answer_handler, json

app = FastAPI()

@app.get("/answer")
async def vonage_answer(request: Request):
    event = {"requestContext": {"http": {"method": "GET"}}}
    result = answer_handler.handler(event, None)
    return JSONResponse(content=json.loads(result["body"]), status_code=result["statusCode"])
```

### `lambda/Dockerfile` — App Runner container

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir fastapi uvicorn bedrock-agentcore
COPY answer.py .
COPY server.py .
EXPOSE 3000
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "3000"]
```

### Deploy App Runner

```bash
# 1. Build and push image to ECR
DOCKER=/Applications/Docker.app/Contents/Resources/bin/docker
ECR_URI="589536902306.dkr.ecr.us-east-1.amazonaws.com/vonage-agentcore-answer"
TMPDIR=$(mktemp -d)

cd lambda/
$DOCKER build --platform linux/amd64 -t vonage-agentcore-answer .
$DOCKER tag vonage-agentcore-answer:latest $ECR_URI:latest

ECR_PASS=$(AWS_PROFILE=vonage-dev aws ecr get-login-password --region us-east-1)
echo "$ECR_PASS" | DOCKER_CONFIG="$TMPDIR" $DOCKER login --username AWS --password-stdin 589536902306.dkr.ecr.us-east-1.amazonaws.com
DOCKER_CONFIG="$TMPDIR" $DOCKER push $ECR_URI:latest

# 2. Create App Runner service
AWS_PROFILE=vonage-dev aws apprunner create-service \
  --service-name vonage-agentcore-answer \
  --source-configuration '{
    "ImageRepository": {
      "ImageIdentifier": "589536902306.dkr.ecr.us-east-1.amazonaws.com/vonage-agentcore-answer:latest",
      "ImageRepositoryType": "ECR",
      "ImageConfiguration": {
        "Port": "3000",
        "RuntimeEnvironmentVariables": {
          "AGENTCORE_RUNTIME_ARN": "<runtime-arn>",
          "VONAGE_NUMBER": "<vonage-number>",
          "AWS_DEFAULT_REGION": "us-east-1"
        }
      }
    },
    "AuthenticationConfiguration": {
      "AccessRoleArn": "arn:aws:iam::589536902306:role/vonage-apprunner-ecr-access-role"
    }
  }' \
  --instance-configuration '{"InstanceRoleArn": "arn:aws:iam::589536902306:role/vonage-apprunner-instance-role"}' \
  --region us-east-1

# → copy ServiceUrl → set as Vonage Answer URL in dashboard
```

### IAM permissions for App Runner instance role

The instance role (`vonage-apprunner-instance-role`) needs:
- `AmazonBedrockFullAccess`
- `BedrockAgentCoreFullAccess`

The ECR access role (`vonage-apprunner-ecr-access-role`) needs:
- Trust: `build.apprunner.amazonaws.com`
- Policy: `AWSAppRunnerServicePolicyForECRAccess`

---

## Component 2 — AgentCore Runtime Container (`runtime/agent.py`)

**What changes from `app/agent.py`:**

|                         | `app/agent.py` (local dev) | `runtime/agent.py` (production)  |
| ----------------------- | -------------------------- | -------------------------------- |
| Port                    | 8000                       | **8080** (AgentCore requirement) |
| App wrapper             | `FastAPI()`                | **`BedrockAgentCoreApp()`**      |
| `/answer` endpoint      | ✅ Present                 | ❌ Removed — Lambda handles it   |
| `/ws` endpoint          | ✅ Present                 | ✅ Kept                          |
| `/hangup` endpoint      | ✅ Present                 | ✅ Kept                          |
| `VonageFrameSerializer` | ✅                         | ✅ Unchanged                     |
| Pipecat pipeline        | ✅                         | ✅ Unchanged                     |
| Nova Sonic              | ✅                         | ✅ Unchanged                     |
| AgentCore bootstrap     | optional                   | remove — agent IS AgentCore      |
| AWS credentials         | `AWS_PROFILE` / `.env`     | IMDS — automatic                 |

### `runtime/agent.py` — key structural change

```python
from bedrock_agentcore.runtime import BedrockAgentCoreApp
from starlette.websockets import WebSocket

app = BedrockAgentCoreApp()

@app.websocket
async def ws_handler(websocket: WebSocket, context) -> None:
    await websocket.accept()  # ← REQUIRED: BedrockAgentCoreApp does not auto-accept
    # ... VonageFrameSerializer + FastAPIWebsocketTransport setup (unchanged from app/agent.py)

if __name__ == "__main__":
    app.run(port=8080)
```

> **Critical:** `BedrockAgentCoreApp` does NOT call `websocket.accept()` before routing to your handler.
> Without `await websocket.accept()`, the pipeline starts, detects a stale connection, and immediately disconnects.
> This is confirmed by c6. The existing `app/agent.py` already does this correctly (line ~138).

### AWS credentials inside AgentCore Runtime

```python
# No .env, no AWS_PROFILE, no static keys needed
# boto3 automatically uses IMDS credentials inside the runtime container
import boto3
aws_session = boto3.Session(region_name=os.getenv("AWS_REGION", "us-east-1"))
```

Remove the `aws_profile` credential branch from `app/agent.py` for the runtime version.

### Deploy to AgentCore Runtime

```bash
cd runtime/
agentcore configure -e agent.py -r us-east-1
# Select: Direct Code Deploy, Python 3.11
agentcore deploy
# → copy Runtime ARN → set as AGENTCORE_RUNTIME_ARN in Lambda env
```

---

## Component 3 — Local Dev (Zero Changes)

```bash
# Exactly as today — nothing changes
docker compose up
ngrok http --domain=your-reserved-domain.ngrok.app 8000
```

Local dev uses `app/agent.py` with `/answer`, `/ws`, port 8000, and ngrok.
No Lambda, no AgentCore Runtime. Developer gets a working agent immediately.

---

## Repo Structure (target)

```
vonage-pipecat-serializer-voice-aws-agentcore/
│
├── app/
│   └── agent.py            # LOCAL DEV — unchanged, full FastAPI app, port 8000
│
├── runtime/
│   └── agent.py            # PRODUCTION — BedrockAgentCoreApp, port 8080, no /answer
│   └── requirements.txt    # pipecat-ai[aws-nova-sonic,websocket]>=1.3.0, bedrock-agentcore, uvicorn
│
├── lambda/
│   └── answer.py           # PRODUCTION — /answer handler, presigned URL → NCCO
│   └── server.py           # PRODUCTION/LOCAL — FastAPI wrapper used by App Runner + ngrok dev
│   └── Dockerfile          # PRODUCTION — App Runner container image
│   └── requirements.txt    # bedrock-agentcore, fastapi, uvicorn
│
├── docker-compose.yml      # LOCAL DEV — unchanged
├── .env.example            # LOCAL DEV — unchanged
└── README.md               # Public README
```

---

## End-to-End Production Call Flow (✅ fully confirmed)

```
1. Caller dials Vonage number

2. Vonage sends GET /answer
   → App Runner public HTTPS endpoint receives request
   → Calls AgentCoreRuntimeClient.generate_presigned_url()
   → Returns NCCO with pre-signed AgentCore WSS URL

3. Vonage connects to AgentCore WSS using pre-signed URL
   → AgentCore Runtime routes wss://.../runtimes/{arn}/ws → container /ws
   → BedrockAgentCoreApp calls @app.websocket handler
   → websocket.accept() completes handshake
   → FastAPIWebsocketTransport + VonageFrameSerializer initializes
   → Pipecat pipeline starts

4. Real-time conversation
   → Vonage streams PCM audio (640-byte frames, 16kHz mono, 20ms)
   → VonageFrameSerializer deserializes binary frames → InputAudioRawFrame
   → Nova Sonic processes speech-to-speech
   → Audio response streams back over WebSocket → Vonage caller

5. Call ends
   → WebSocket closes cleanly
   → Pipecat pipeline tears down
```

---

## Deployment Steps — Complete End-to-End

```bash
# Step 1 — Deploy agent to AgentCore Runtime
cd runtime/
agentcore configure -e agent.py -r us-east-1
# Select: Direct Code Deploy, Python 3.12
agentcore deploy
# → copy Runtime ARN from output

# Step 2 — Build and push App Runner image (see Component 1 above for full commands)
cd lambda/
docker build --platform linux/amd64 -t vonage-agentcore-answer .
# push to ECR, create App Runner service
# → copy App Runner ServiceUrl from output

# Step 3 — Update Vonage Dashboard
# Set Answer URL: https://{service-id}.{region}.awsapprunner.com/answer
```

**Total AWS resources:** 1 App Runner service + 1 AgentCore Runtime + 1 ECR repo. No servers, no ALB, no API Gateway.

---

## Why This Is the Right Path

| Goal | Status |
|---|---|
| Local dev unchanged | ✅ `app/agent.py` untouched — confirmed working |
| `VonageFrameSerializer` runs inside AgentCore Runtime | ✅ Confirmed by c6 (WebSocket probe) |
| `/answer` generates valid NCCO with presigned URL | ✅ Confirmed — App Runner `GET /answer` verified via `curl` |
| Vonage connects to AgentCore via presigned URL | ✅ Confirmed — real Vonage call tested |
| Full audio round-trip with Nova Sonic | ✅ Confirmed — real Vonage call, agent responded |
| Publicly reachable `/answer` within SCP constraints | ✅ App Runner — not subject to `lambda:InvokeFunctionUrl` SCP |

---

## Notes on `pipecat-ai` Package

`VonageFrameSerializer` is in the upstream `pipecat-ai` package on PyPI — **no Vonage fork needed.**

```
pipecat-ai[aws-nova-sonic,websocket]>=1.3.0
```

The serializer was merged from the `Vonage/pipecat` fork into the upstream repo.

> **Critical (confirmed c8):** Use `pipecat-ai[aws-nova-sonic,websocket]>=1.3.0` — NOT `pipecat-ai[aws]`.
> The `aws-nova-sonic` extra installs `aws_sdk_bedrock_runtime`, which PyPI restricts to **Python >= 3.12**.
> On Python 3.11 it installs silently without it, causing `ModuleNotFoundError` at runtime.
> The `websocket` extra is required for `FastAPIWebsocketTransport`.
> Runtime must be deployed with `runtime_type: PYTHON_3_12`.

---

## Account-Level SCP Restrictions (account 589536902306)

> **This section is specific to this AWS account.** The architecture above uses App Runner to work within these constraints.

This account is under org `o-e48k2noeyt` (master: `aws-vng-master-account@vonage.com`).
An SCP blocks:
- `lambda:InvokeFunctionUrl` — public Function URL returns HTTP 403 (even with `AuthType: NONE` and `Principal: *` resource policy)
- `apigateway:*` — fully blocked

**IAM `simulate-principal-policy` returns `allowed` for all of these — it does not evaluate SCP denials.**

**Resolution:** App Runner is used in production instead. App Runner provides a public HTTPS endpoint not subject to these SCP restrictions. Deployed and confirmed working: `https://shs62gbuks.us-east-1.awsapprunner.com/answer`

### For standard AWS accounts (no SCP)

Lambda Function URL is simpler and cheaper. Replace App Runner with:

```bash
cd lambda/
zip lambda.zip answer.py
aws lambda create-function \
    --function-name vonage-answer \
    --runtime python3.12 \
    --handler answer.handler \
    --zip-file fileb://lambda.zip \
    --role arn:aws:iam::{account}:role/vonage-answer-role \
    --environment Variables="{AGENTCORE_RUNTIME_ARN=...,VONAGE_NUMBER=...,AWS_DEFAULT_REGION=us-east-1}"

aws lambda create-function-url-config --function-name vonage-answer --auth-type NONE
# → Set Function URL as Vonage Answer URL
```

### Local dev with ngrok (no App Runner needed)

Run `lambda/server.py` locally for development:

```bash
cd lambda/
pip install -r requirements.txt
AGENTCORE_RUNTIME_ARN="arn:aws:bedrock-agentcore:us-east-1:589536902306:runtime/vonage_runtime_agent-GC5gEQBPPz" \
VONAGE_NUMBER="+12012791019" AWS_PROFILE=vonage-dev \
    uvicorn server:app --host 0.0.0.0 --port 3000
# In another terminal:
ngrok http 3000
# Set Vonage Answer URL → https://<ngrok-id>.ngrok.io/answer
```

---

- [c5 reference — upstream `aws-agentcore` example analysis](tests2/c5_pipecat_agentcore_ws/README.md)
- [c6 smoke test — VonageFrameSerializer inside AgentCore Runtime (PASSED)](tests2/c6_agentcore_ws_serializer_smoke/README.md)
- [BedrockAgentCoreApp source](https://github.com/aws/bedrock-agentcore-sdk-python/blob/main/src/bedrock_agentcore/runtime/app.py)
- [AgentCoreRuntimeClient source](https://github.com/aws/bedrock-agentcore-sdk-python/blob/main/src/bedrock_agentcore/runtime/agent_core_runtime_client.py)
- [Vonage Pipecat Serializer docs](https://developer.vonage.com/en/video/guides/vonage-pipecat-serializer-overview)
