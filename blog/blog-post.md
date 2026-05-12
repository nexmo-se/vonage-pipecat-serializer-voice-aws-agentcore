# Building a Voice AI Agent with Vonage Audio Serializer, Pipecat, and AWS Bedrock AgentCore

## Overview

What if a customer could call a phone number and speak to an AI agent that not only understands natural conversation — but can also look up their account, check inventory, or book an appointment in real time?

This post walks through a reference implementation that wires together three AWS and Vonage services to make exactly that possible:

- **Vonage Audio Serializer for Pipecat** — Streams live phone call audio over WebSocket into a Pipecat pipeline
- **AWS Bedrock Nova Sonic** — Processes voice directly (speech-in, speech-out) with no STT/TTS roundtrip
- **AWS Bedrock AgentCore** — Provides the agent runtime: tool calling, RAG over private knowledge, and real-world integrations

---

## The Problem: Traditional Voice AI is Fragmented

Typical voice AI stacks look like this:

```
Phone call audio → STT (transcription) → LLM (text) → TTS (synthesis) → Audio back
```

Every hop adds latency. A conversation turn can take 3–5 seconds. Callers notice.

There's also a data loss problem: STT drops prosody, tone, and nuance. The LLM reasons on flat text, not the richness of speech.

---

## The Solution: Speech-to-Speech with a Real Agent Behind It

This stack collapses the chain:

```
Phone call audio → Nova Sonic (voice in, voice out) → AgentCore (tools + knowledge) → Audio back
```

Nova Sonic understands and responds to voice directly. When it needs to take action or answer from private data, it invokes AgentCore. The caller hears a response in under a second.

### Why the Vonage Audio Serializer?

Vonage offers two Pipecat integrations:

| Transport                        | Use case                                                   |
| -------------------------------- | ---------------------------------------------------------- |
| **Video Connector** (WebRTC)     | Full video + audio applications                            |
| **Audio Serializer** (WebSocket) | Voice-only AI — simpler, lower latency, no WebRTC overhead |

For a voice agent, the Audio Serializer is the right choice. It streams raw PCM audio over a WebSocket connection — exactly what Nova Sonic expects — without the weight of a WebRTC stack.

### Why AgentCore?

Nova Sonic is a powerful conversational model, but it only knows what it was trained on. AgentCore extends it with:

- **Tool calling** — live weather, CRM lookups, booking systems, databases
- **Knowledge bases (RAG)** — answer from your own documents, not training data
- **Managed runtime** — deploy agent logic as a serverless function, no infra to manage

The result: a voice agent that can have a natural conversation _and_ actually do something useful.

---

## Architecture

```
Caller dials Vonage number
  ↓
Vonage Voice API receives call
  ↓  returns NCCO with wss:// WebSocket endpoint
Vonage connects call audio to agent over WebSocket
  ↓  PCM 16-bit, 16kHz, 640-byte frames
Vonage Audio Serializer Transport  (Pipecat)
  ↓
AWSNovaSonicLLMService             (Pipecat)
  ↓  when tools/knowledge needed
AWS Bedrock AgentCore              (invoke_agent_runtime)
  ↓
Audio response streams back to caller
```

### Key components

**`VonageFrameSerializer`** — Pipecat component that handles the Vonage WebSocket audio protocol: deserializes incoming PCM frames from the call, serializes outgoing PCM frames back to the caller.

**`FastAPIWebsocketTransport`** — The FastAPI WebSocket server that Vonage connects to. Configured with `fixed_audio_packet_size=640` to match Vonage's 20ms PCM frame size.

**`AWSNovaSonicLLMService`** — Pipecat service that streams audio to AWS Bedrock Nova Sonic over a bidirectional Bedrock stream. Receives audio back as PCM frames.

**`BedrockAgentCoreApp`** — The AgentCore runtime (deployed separately). Receives structured requests from Nova Sonic and returns tool responses or knowledge-grounded answers.

---

## Pipeline

The Pipecat pipeline is deliberately minimal:

```python
pipeline = Pipeline([
    transport.input(),   # Audio frames from Vonage call
    nova_sonic,          # Speech-to-speech LLM (calls AgentCore when needed)
    transport.output()   # Audio frames back to Vonage call
])
```

No STT. No TTS. No text aggregators. Audio goes in, audio comes out.

On call connect, an `LLMContextFrame` is pushed immediately to initialize the Bedrock stream:

```python
@transport.event_handler("on_client_connected")
async def on_connected(t, client):
    await task.queue_frame(LLMContextFrame(context))
```

This triggers Nova Sonic's `_send_audio_input_start_event()` — without it, the Bedrock stream never opens and audio frames are silently dropped.

---

## Testing Strategy

The `tests/` folder validates each layer independently before you run a live call:

| Test    | Validates                                                  |
| ------- | ---------------------------------------------------------- |
| **C1**  | Vonage credentials + voice call bootstrap                  |
| **C2**  | Audio Serializer WebSocket connectivity                    |
| **C3**  | Pipecat pipeline echo (audio in → audio out)               |
| **C4a** | AWS Bedrock credentials + model access                     |
| **C4b** | Full live call: Vonage → Nova Sonic speech-to-speech       |
| **C5**  | AgentCore runtime: tool invocation from the voice pipeline |

This staged approach means you can debug each integration point in isolation rather than diagnosing a broken end-to-end call.

---

## Key Implementation Details

### Pipecat adapter bug fix

Pipecat 0.0.104 has a bug in `aws_nova_sonic_adapter.py` — `ConvertedMessages()` is called without its required `messages` parameter when the message list is empty. Apply this patch:

```python
# In pipecat/adapters/services/aws_nova_sonic_adapter.py ~line 124
# Before:
return self.ConvertedMessages()
# After:
return self.ConvertedMessages(messages=[])
```

### Audio frame sizing

Vonage sends exactly 640-byte PCM frames (20ms @ 16kHz mono 16-bit). The transport must be configured to match:

```python
params = FastAPIWebsocketParams(
    audio_in_enabled=True,
    audio_out_enabled=True,
    add_wav_header=False,
    fixed_audio_packet_size=640,   # Must match Vonage frame size
    serializer=VonageFrameSerializer(),
    vad_analyzer=SileroVADAnalyzer(),
)
```

### Dynamic NCCO routing

The `/answer` endpoint auto-detects whether the request is HTTP or HTTPS and returns the correct `ws://` or `wss://` WebSocket URI:

```python
@app.get("/answer")
async def answer(request: Request):
    scheme = "wss" if request.url.scheme == "https" else "ws"
    ws_url = f"{scheme}://{request.headers['host']}/ws"
    return JSONResponse([{
        "action": "connect",
        "endpoint": [{"type": "websocket", "uri": ws_url,
                      "content-type": "audio/l16;rate=16000"}]
    }])
```

---

## Running the Demo

### Prerequisites

- Vonage account with voice-enabled number and application
- AWS account with Bedrock Nova Sonic access (`amazon.nova-2-sonic-v1:0` in `us-east-1`)
- AWS Bedrock AgentCore runtime deployed
- ngrok (for local development)

### Quick start

```bash
# 1. Clone and configure
git clone https://github.com/nexmo-se/vonage-pipecat-serializer-voice-aws-agentcore
cd vonage-pipecat-serializer-voice-aws-agentcore
cp .env.example .env
# Fill in VONAGE_APPLICATION_ID, AWS_PROFILE, AGENTCORE_AGENT_ARN, etc.

# 2. Run staged tests to validate each layer
cd tests/c1_voice_call_bootstrap && python test_voice_bootstrap.py  # credentials
cd ../c4b_bedrock_nova_sonic_serializer && python test_bedrock.py   # Bedrock access
cd . && python test_integration.py                                  # full preflight

# 3. Start the live agent
lsof -ti tcp:8001 | xargs kill -9 2>/dev/null || true
source ../c2_voice_linux_sdk/venv/bin/activate
WS_PORT=8001 AWS_PROFILE=vonage-dev python bedrock_echo_agent.py

# 4. Expose with ngrok and update Vonage dashboard Answer URL
ngrok http --domain=your-domain.ngrok.app 8001

# 5. Call your Vonage number
```

See `tests/c4b_bedrock_nova_sonic_serializer/README.md` for the full 7-phase walkthrough with expected outputs and troubleshooting.

---

## Repository Structure

```
app/                          Production FastAPI app (Dockerfile + full agent)
tests/
  c1_voice_call_bootstrap/   Vonage credentials validation
  c2_voice_linux_sdk/        Audio Serializer connectivity
  c3_pipecat_serializer/     Pipecat pipeline echo test
  c4a_bedrock_preflight/     Bedrock credentials + model access
  c4b_bedrock_nova_sonic_serializer/  Live voice agent (main demo)
  c5_agentcore_runtime/      AgentCore tool invocation
blog/                         This post
```

---

## What's Next

This reference implementation gives you the working end-to-end plumbing. From here you can:

- **Add tools to AgentCore** — connect a CRM, calendar, database, or REST API
- **Add a knowledge base** — RAG over your product docs, policies, or FAQs
- **Customize Nova Sonic's persona** — change the system prompt for domain-specific agents
- **Deploy to production** — use the `app/` Docker container with a cloud WebSocket endpoint

The Vonage Audio Serializer + Nova Sonic + AgentCore combination is a complete foundation for building voice AI agents that go beyond conversation and actually get things done.
