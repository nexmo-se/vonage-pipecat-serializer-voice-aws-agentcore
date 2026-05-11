# C3 — Pipecat Serializer Echo

Validates the full Pipecat pipeline with Vonage Audio Serializer running an echo agent that processes and returns audio in real-time.

> **Architecture:** This test runs a FastAPI + Pipecat WebSocket server with the Vonage Audio Serializer. Vonage Voice API routes inbound calls to this server via NCCO connect action. Audio flows bidirectionally through the Pipecat pipeline and is echoed back to the caller.

## Prerequisites

1. **C1 and C2 completed** — Call session established and Audio Serializer prerequisites verified
2. **Python 3.13+** with all Pipecat dependencies installed
3. **Valid Vonage credentials** — From `.env` (auto-populated by C1)

## Core dependencies

C3 requires three essential components:

| Dependency  | Purpose                                                               | Why Required                                                        |
| ----------- | --------------------------------------------------------------------- | ------------------------------------------------------------------- |
| **FastAPI** | Creates WebSocket `/ws` endpoint and HTTP `/status`, `/health` routes | Handles Vonage WebSocket connections and provides health monitoring |
| **uvicorn** | ASGI server that runs the FastAPI application                         | Without it, no server runs; Vonage has no endpoint to connect to    |
| **loguru**  | Logger for `logger.enable("pipecat")`                                 | Enables verbose Pipecat framework logging for debugging             |

These are installed via `requirements.txt` and cannot be omitted.

## Run commands

### Native (Linux/macOS)

```bash
cd tests/c3_pipecat_serializer
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -r requirements.txt
python serializer_echo_bot.py
```

Server starts on `ws://0.0.0.0:8000/ws`. Press **Ctrl+C** to stop.

### Docker (recommended)

```bash
cd /path/to/vonage-pipecat-serializer-voice-aws-agentcore
docker compose run --rm c3-pipecat-serializer
```

## Expected output

### Startup (immediate)

```
2026-05-11 13:17:57.164 | INFO | pipecat:<module>:14 - ᓚᘏᗢ Pipecat 0.0.104.post2.dev1 (Python 3.14.4) ᓚᘏᗢ
Pipecat Vonage Echo Bot WebSocket Server
  Listening on ws://0.0.0.0:8000/ws
  Waiting for Vonage Voice API connections ...

To route Vonage calls to this server:
  1. In Voice Playground, create NCCO with WebSocket connect action:
     wss://your.domain/ws  (replace with public endpoint)
  2. Call the phone number to start processing

Press Ctrl+C to stop server.

INFO:     Uvicorn running on http://0.0.0.0:8000
INFO:     Application startup complete
```

**✅ Test passed if:**

- `Listening on ws://0.0.0.0:8000/ws` appears
- `Application startup complete` is shown
- No import errors or port conflicts
- Server runs until you press Ctrl+C

### During active connection (after Vonage call routed to /ws)

```
✓ Vonage connected: 192.168.1.100:54321
  Echo pipeline started for 192.168.1.100:54321
  Audio from Vonage → echoed back
  Vonage disconnected: 192.168.1.100:54321
✓ Connection closed: 192.168.1.100:54321
```

## What this test does

1. **WebSocket Server** — Pipecat starts a FastAPI server listening on ws://0.0.0.0:8000/ws
2. **Vonage Connection** — Vonage Voice API connects via NCCO WebSocket connect action
3. **Audio Serializer** — VonageFrameSerializer converts between Vonage PCM audio and Pipecat frames
4. **Echo Pipeline** — Audio frames pass directly through input → output (echo behavior)
5. **Bidirectional Flow** — Audio flows from caller → Pipecat → back to caller in real-time

## What constitutes a passing test

✅ **C3 passes when:**

1. Server starts without import errors
2. Uvicorn binds to port 8000 (or configured `WS_PORT`)
3. WebSocket endpoint `/ws` is listening
4. Application startup completes successfully
5. Server remains running until manual Ctrl+C
6. No connection errors or crash logs

**Note:** C3 validates the _infrastructure_ (server startup, serializer init, WebSocket binding). Actual audio processing happens when Vonage routes calls to the endpoint (typically done in real Voice API integration, not in this test environment).

## Troubleshooting

| Issue                                                       | Solution                                                            |
| ----------------------------------------------------------- | ------------------------------------------------------------------- |
| `ImportError: No module named 'pipecat.serializers.vonage'` | Pipecat fork not properly installed; check git clone of custom fork |
| `ModuleNotFoundError: No module named 'fastapi'`            | Run `pip install -r requirements.txt`                               |
| `Address already in use` (port 8000)                        | Change port: `WS_PORT=8001 python serializer_echo_bot.py`           |
| Server starts but no connections                            | Verify Vonage NCCO routes calls to correct WebSocket endpoint       |
| `WebSocketDisconnect` immediately                           | Call may have terminated; check Vonage Voice Playground logs        |

## Environment variables

Optional overrides in `.env`:

```
WS_HOST=0.0.0.0           # WebSocket server bind address
WS_PORT=8000              # WebSocket server port
VONAGE_ENABLE_PIPECAT_LOGGER=1  # Enable verbose Pipecat logging
```

## Next steps

After C3 passes ✅, proceed to:

- **C4a** — AWS Bedrock preflight check (validate Bedrock access)
- **C4b** — Bedrock Nova Sonic integration (speech-to-speech end-to-end test)
- **C5** — AgentCore runtime (optional bootstrap validation)
