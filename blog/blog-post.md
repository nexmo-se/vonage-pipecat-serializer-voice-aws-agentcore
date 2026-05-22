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

- An AI agent deployed for voice calls on your Vonage number
- Real-time spoken AI responses using AWS Nova Sonic
- Optional AgentCore integration for tool calling, RAG, and external API access
- A deployment-ready architecture for EC2, ECS/Fargate, or EKS

## Prerequisites

Before you begin, make sure you have the following:

- A Vonage API account with Voice API enabled and a phone number linked to a Voice application
- An AWS account with Amazon Bedrock access and Nova Sonic (`amazon.nova-2-sonic-v1:0`) enabled in `us-east-1`
- Docker Desktop — the app runs in Docker for an isolated, reproducible runtime
- ngrok with a reserved domain for a stable Vonage webhook URL
- AWS CLI configured (`aws configure --profile vonage-dev`)

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

_Architecture overview: Vonage Voice API → Audio Serializer → Pipecat pipeline → AWS Nova Sonic → AgentCore._

```
Caller dials Vonage number
  ↓
Vonage Voice API
  ↓ GET /answer → returns NCCO
  ↓ Vonage connects WebSocket to /ws
  ↓ WebSocket (PCM 16-bit, 16kHz)
Vonage Audio Connector Server SDK
(manages WebSocket session)
  ↓
Vonage Pipecat Serializer
(converts PCM frames ↔ Pipecat internal format)
  ↓
Pipecat Pipeline
  ↓
AWS Bedrock Nova Sonic
(speech-to-speech — voice in, voice out)
  ↓ optional
AWS Bedrock AgentCore
(tools, RAG, external APIs)
  ↓
Audio response streams back to caller
```

| Component                           | Role                                                             |
| ----------------------------------- | ---------------------------------------------------------------- |
| Vonage Voice API                    | Telephony — incoming phone calls via NCCO WebSocket connect      |
| Vonage Audio Connector Server SDK   | Manages the WebSocket connection between Vonage and your server  |
| Vonage Pipecat Serializer           | Converts Vonage PCM audio frames to/from Pipecat internal format |
| Vonage Audio Serializer for Pipecat | Real-time media and model orchestration                          |
| Amazon Nova Sonic                   | Low-latency speech-to-speech intelligence                        |
| Amazon Bedrock AgentCore            | Managed runtime for deployable agent logic                       |

## Step 1 — Clone the Repository

```bash
git clone https://github.com/nexmo-se/vonage-pipecat-serializer-voice-aws-agentcore.git
cd vonage-pipecat-serializer-voice-aws-agentcore
```

The repository layout:

```
vonage-pipecat-serializer-voice-aws-agentcore/
├── app/                 # Pipecat agent runtime (agent.py, server.py)
├── tests/               # Isolated component validation scripts
├── docker-compose.yml   # Container orchestration
├── requirements.txt     # Python dependencies
├── .env.example         # Environment variable template
└── README.md
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
VONAGE_CALL_ID=your-vonage-call-id

# AWS
AWS_PROFILE=vonage-dev
AWS_REGION=us-east-1
BEDROCK_MODEL_ID=amazon.nova-2-sonic-v1:0
BEDROCK_CONNECT_TIMEOUT_SECONDS=10
BEDROCK_READ_TIMEOUT_SECONDS=60
BEDROCK_MAX_ATTEMPTS=4
BEDROCK_VALIDATE_MODEL_ID=true

# AgentCore (optional — leave blank to skip bootstrap)
AGENTCORE_AGENT_ARN=arn:aws:bedrock-agentcore:us-east-1:123456789012:runtime/your-runtime-id

# Nova Sonic session guard
NOVA_SESSION_WARN_SECONDS=410
NOVA_SESSION_LIMIT_SECONDS=470
NOVA_SESSION_STOP_ON_LIMIT=false

# Agent behavior
BEDROCK_SYSTEM_INSTRUCTION=You are a helpful voice assistant. Respond warmly and briefly.
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

The `agent.py` implements a `VonageSerializerVoiceAgent` class — one instance per inbound Vonage WebSocket connection. The Vonage Pipecat Serializer handles all PCM audio frame conversion between Vonage's WebSocket format and Pipecat's internal pipeline format.

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

## Step 4 — Add AgentCore Bootstrap (Optional)

When `AGENTCORE_AGENT_ARN` is set, the agent invokes AgentCore once at session start to fetch a priming message. This message is injected into the Pipecat pipeline before the conversation begins — enabling tool use, RAG, and external API calls.

```python
# Optional AgentCore bootstrap — invoked once at session start
bootstrap_message = await invoke_agentcore_bootstrap(agentcore_bootstrap_prompt)

context_messages = []
if bootstrap_message:
    context_messages.append({
        "role": "user",
        "content": (
            "Use the following context to shape your first response: "
            f"{bootstrap_message}"
        ),
    })

context = LLMContext(messages=context_messages)

# Push context into pipeline when Vonage WebSocket connects
@transport.event_handler("on_client_connected")
async def on_client_connected(t, client):
    await pipeline_task.queue_frame(LLMContextFrame(context))
```

To deploy your own AgentCore agent:

```bash
pip install bedrock-agentcore-starter-toolkit
agentcore configure -e agent.py -r us-east-1
agentcore deploy

# Copy the Runtime ARN → add to .env as AGENTCORE_AGENT_ARN
```

## Step 5 — Make a Test Call

Call your Vonage number. When Vonage requests `GET /answer`, the app returns an NCCO that connects the call audio to the agent over WebSocket:

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

The full call flow is:

1. Vonage requests `GET /answer`
2. App returns NCCO with `wss://your-domain.ngrok.app/ws`
3. Vonage streams call audio over WebSocket to `/ws`
4. Vonage Audio Connector Server SDK manages the WebSocket session
5. Vonage Pipecat Serializer converts PCM frames into Pipecat format
6. Nova Sonic processes speech and responds in real time
7. If AgentCore is enabled, it handles tool calls and knowledge base queries

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
boto3>=1.34.0
pipecat-ai[aws,aws-nova-sonic,silero] @ git+https://github.com/Vonage/pipecat.git
fastapi>=0.110.0
uvicorn[standard]>=0.29.0
bedrock-agentcore>=0.1.0
structlog>=24.1.0
```

> **Note:** This project uses the Vonage fork of pipecat (`git+https://github.com/Vonage/pipecat.git`) which includes the latest Vonage Audio Serializer updates.

## Deploying to Production

`docker compose` is for local development only. Here are three recommended paths for deploying this agent to production.

### Option 1 — EC2 (Fastest Path)

Best for: quick production deployments, single-region, predictable call volume.

```bash
# Launch an EC2 instance (Ubuntu 22.04, t3.medium minimum)
# SSH into the instance and install Docker
sudo apt-get update && sudo apt-get install -y docker.io docker-compose-plugin

# Clone the repo
git clone https://github.com/nexmo-se/vonage-pipecat-serializer-voice-aws-agentcore.git
cd vonage-pipecat-serializer-voice-aws-agentcore

# Configure environment
cp .env.example .env
# Edit .env with your credentials

# Run
docker compose --profile app up -d --build app
```

Attach an IAM role to the EC2 instance with `AmazonBedrockFullAccess` and `BedrockAgentCoreFullAccess` — no static AWS keys needed.

Set your Vonage Voice application Answer URL to your EC2 public IP or domain:

```
https://your-ec2-domain.com/answer
```

### Option 2 — ECS/Fargate (Recommended at Scale)

Best for: auto-scaling, managed infrastructure, high call volume.

```bash
# Build and push image to ECR
aws ecr create-repository --repository-name vonage-pipecat-serializer
docker build -t vonage-pipecat-serializer .
docker tag vonage-pipecat-serializer:latest \
  123456789012.dkr.ecr.us-east-1.amazonaws.com/vonage-pipecat-serializer:latest
docker push \
  123456789012.dkr.ecr.us-east-1.amazonaws.com/vonage-pipecat-serializer:latest
```

Key ECS configuration:

- **Task CPU/Memory:** 1 vCPU / 2GB minimum per agent instance
- **IAM Task Role:** attach `AmazonBedrockFullAccess` + `BedrockAgentCoreFullAccess`
- **Networking:** VPC with public subnet or NAT Gateway for Bedrock API access
- **Scaling:** target tracking on CPU utilization or active call count metric
- **Load balancer:** ALB with sticky sessions for `/ws` WebSocket connections

### Option 3 — EKS (Enterprise Scale)

Best for: multi-tenant deployments, existing Kubernetes infrastructure, advanced traffic management.

```yaml
# deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: vonage-pipecat-serializer
spec:
  replicas: 3
  template:
    spec:
      containers:
        - name: agent
          image: 123456789012.dkr.ecr.us-east-1.amazonaws.com/vonage-pipecat-serializer:latest
          ports:
            - containerPort: 8000
          envFrom:
            - secretRef:
                name: vonage-pipecat-secrets
          resources:
            requests:
              cpu: "1"
              memory: "2Gi"
```

## Production Checklist

- Use IAM roles — never static AWS keys in production
- Store secrets in AWS Secrets Manager or Parameter Store
- Enable CloudWatch metrics and CloudTrail auditing
- Configure ALB with sticky sessions for WebSocket connections
- Set `NOVA_SESSION_WARN_SECONDS` and implement session renewal for long calls
- Configure health checks on `GET /` for load balancer
- Set Vonage Answer URL to your production domain before go-live

## Conclusion

You have deployed a real-time AI agent for voice calls using the Vonage Audio Serializer for Pipecat and AWS Nova Sonic. The Vonage Audio Connector Server SDK manages the WebSocket session, the Vonage Pipecat Serializer bridges phone call audio into the Pipecat pipeline, and AgentCore enables the agent to take real-world actions beyond its training data.

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
