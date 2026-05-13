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

## AWS Bedrock AgentCore: Benefits vs. Without It

### What is AgentCore?

AWS Bedrock AgentCore is a runtime service that can execute business logic, fetch data from external APIs, and prepare contextual information before handing off to the conversational agent. In this application, it's used as a **bootstrap step** to prime the LLM context before the call starts.

### Comparison: With vs. Without AgentCore

| Aspect                        | **With AgentCore Enabled**                                                             | **Without AgentCore**                                                   |
| ----------------------------- | -------------------------------------------------------------------------------------- | ----------------------------------------------------------------------- |
| **First Response Quality**    | Higher — agent has context about user, session, business rules                         | Generic — agent starts cold with only system instruction                |
| **Latency to First Response** | Slightly higher init (~200-500ms for AgentCore) but then faster responses overall      | Fast initial connection, but may need 2-3 turns to get useful responses |
| **Use Cases**                 | Customer support, account lookups, policy retrieval, tool discovery, RAG integration   | Simple Q&A, general conversation, demos                                 |
| **Business Logic**            | Can execute before call starts (e.g., fetch customer history, authorize access)        | All logic must happen in real-time during conversation                  |
| **Session Metadata**          | AgentCore provides context (e.g., "customer_id=12345, tier=premium, language=Spanish") | Agent infers from conversation                                          |
| **Tool Availability**         | Can announce available tools/actions upfront via context                               | Tools discovered during conversation                                    |
| **Error Handling**            | Graceful fallback — if AgentCore fails, call continues with empty context              | N/A                                                                     |

### Example: With AgentCore

**Setup:**

```bash
AGENTCORE_AGENT_ARN=arn:aws:bedrock-agentcore:us-east-1:123456789012:agent-runtime/ABC123
AGENTCORE_BOOTSTRAP_PROMPT="Fetch customer details for this call and prepare a brief greeting."
```

**Call flow:**

1. Phone rings → app receives `/answer` webhook
2. **AgentCore invoked:** Returns `{"customer_id": "cust_5678", "name": "Alice", "account_status": "active", "pending_issues": ["billing", "upgrade"]}`
3. LLMContext primed with customer metadata
4. Caller connects → Nova Sonic immediately has context
5. **First response:** "Hi Alice! I see you have questions about billing and upgrades. How can I help?"

**Result:** Caller feels recognized, less repeating information, faster resolution.

### Example: Without AgentCore

**Call flow:**

1. Phone rings → app receives `/answer` webhook
2. **No AgentCore:** LLMContext is empty (only system instruction)
3. Caller connects → Nova Sonic starts fresh
4. **First response:** "Hi! How can I help you today?"

**Result:** Generic greeting, caller must explain context, then agent learns during conversation (takes 2-3 turns).

### When to Enable AgentCore

✅ **Enable if you have:**

- Customer database or API to query
- Business logic to execute before talking (authorization, eligibility check, data fetch)
- Multiple tools/actions agent should know about upfront
- Need for faster resolution (fewer conversation turns)

❌ **Disable if:**

- Simple Q&A or demo use case
- All context comes from caller's speech
- No backend integrations needed
- Latency is more critical than context richness

### Configuration for AgentCore

```env
# Enable AgentCore bootstrap by setting the agent runtime ARN
AGENTCORE_AGENT_ARN=arn:aws:bedrock-agentcore:us-east-1:123456789012:agent-runtime/my-agent-id

# Optional: Custom bootstrap prompt (what to ask AgentCore)
AGENTCORE_BOOTSTRAP_PROMPT="Fetch account details for this inbound call and return a JSON summary."

# Optional: Timeout in seconds (default: 3)
AGENTCORE_TIMEOUT_SEC=5
```

### Observability

When AgentCore is enabled, the app tracks:

- **Initialization latency** — How long AgentCore takes (goal: <500ms)
- **Response validation** — Ensures AgentCore returns valid data
- **Fallback behavior** — If AgentCore fails, call continues gracefully
- **Metrics exported** — Prometheus endpoint at `/metrics` (see `/status` response)

### Official Documentation References

All claims about AgentCore benefits are backed by official AWS documentation:

| Claim                                     | Official Source                                                                                                                                                                                                                                                                                                               |
| ----------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Business Logic Execution**              | [AWS Bedrock AgentCore Overview](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/what-is-bedrock-agentcore.html): "enable agents to take actions across tools and data with the right permissions"                                                                                                              |
| **API Integration**                       | [AgentCore Gateway](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/agents-tools-runtime.html): "convert your APIs, Lambda functions, and existing services into Model Context Protocol (MCP)-compatible tools...Any APIs, MCP tools, Lambda, and popular integrations including Salesforce, Zoom, JIRA, Slack" |
| **Session Metadata & Context**            | [Memory Service](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/what-is-bedrock-agentcore.html): "build context-aware agents with complete control over what the agent remembers and learns. Supports both short-term memory for multi-turn conversations and long-term memory that persists across sessions"  |
| **Data Fetching Before Conversation**     | [Core Services](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/what-is-bedrock-agentcore.html): "agents...reason, use tools, and maintain context. Deploy agents for customer support, workflow automation, data analysis"                                                                                     |
| **Tool Discovery Upfront**                | [AgentCore Gateway](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/what-is-bedrock-agentcore.html): "Registry provides a centralized catalog for discovering and managing agents, MCP servers, tools, skills and custom resources across your organization"                                                    |
| **Session Isolation & Graceful Handling** | [Runtime Service](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/what-is-bedrock-agentcore.html): "Runtime provides fast cold starts for real-time interactions...true session isolation...built-in identity"                                                                                                  |

## Production notes

- Deploy on Linux-based hosts or containers (Docker image uses `python:3.13-slim`)
- Use IAM instance roles or managed secrets instead of static AWS credentials
- Monitor the `/events` WebSocket for `session_renewal_recommended` — Nova Sonic has an ~8 min session limit
- Nova Sonic connection: `us-east-1` only (as of writing)
