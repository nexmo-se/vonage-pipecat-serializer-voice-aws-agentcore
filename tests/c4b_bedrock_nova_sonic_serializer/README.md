# C4b — Bedrock Nova Sonic + Audio Serializer

Full integration test: Vonage Audio Serializer Transport + Pipecat + AWS Bedrock Nova Sonic speech-to-speech processing.

> **Architecture:** Incoming voice from Vonage Voice API → Audio Serializer Transport → Pipecat pipeline → AWS Bedrock Nova Sonic LLM → Response audio → Back to Vonage call

## Prerequisites

1. **C1–C4a completed** — Call session, Serializer connectivity, and Bedrock access verified
2. **Docker or Linux runtime** — Python 3.13+ with WebRTC support
3. **AWS Bedrock access** — Configured model must be available and invocable
4. **Valid Vonage credentials** — From `.env` (populated by C1)

## Run commands

### Validation tests

```bash
cd tests/c4b_bedrock_nova_sonic_serializer
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python test_bedrock.py
python test_integration.py
```

### Live Agent (Docker recommended)

```bash
docker compose run --rm c4b-bedrock-nova-sonic-serializer
```

### Live Agent (Native)

```bash
python bedrock_echo_agent.py
```

## Expected output

### Tests

```
AWS Bedrock Nova Sonic Validation
✓ Bedrock client initialized
✓ Nova Sonic model available
✓ Audio Serializer integration loaded
C4b Tests PASSED ✓
```

### Live Agent

```
Bedrock Nova Sonic + Audio Serializer Agent
Initializing Audio Serializer Transport …
Pipecat pipeline starting …
Joined call: <VONAGE_CALL_ID>
✓ Speech-to-speech agent active (listening for audio)
Press Ctrl+C to exit
```

While connected:

- Incoming speech is transcribed by Nova Sonic
- LLM generates conversational response
- Response is synthesized back to speech
- Audio is sent back to the caller via Vonage

## What's happening

1. **Pipeline Initialization** — Pipecat loads with Vonage Audio Serializer Transport
2. **Audio Capture** — Incoming audio from Vonage is received via WebSocket
3. **Speech Processing** — Audio frames are processed through the pipeline
4. **LLM Processing** — AWS Bedrock Nova Sonic generates conversational response
5. **Speech Synthesis** — Response is converted back to audio format
6. **Audio Response** — Audio is serialized and sent back to Vonage for the caller
7. **Context Management** — Conversation history is maintained for multi-turn dialogue

## Test findings

- ✅ Vonage Audio Serializer Transport integration with Pipecat
- ✅ AWS Bedrock Nova Sonic invocation and response handling
- ✅ Audio serialization/deserialization with correct format conversion
- ✅ Real-time speech-to-speech processing latency
- ✅ LLM context and conversation history management
- ✅ Error handling and graceful shutdown

## Troubleshooting

| Issue                                  | Solution                                                     |
| -------------------------------------- | ------------------------------------------------------------ |
| `Bedrock access denied`                | Verify IAM permissions and `BEDROCK_MODEL_ID` is correct     |
| `Audio Serializer connection failed`   | Re-run C1 to refresh credentials; verify Vonage app ID       |
| `Pipeline initialization timeout`      | Check network connectivity and AWS region configuration      |
| `ImportError: No module named pipecat` | Ensure `requirements.txt` is installed in venv               |
| `VONAGE_CALL_ID missing or expired`    | Complete C1 to get fresh session; calls expire after ~1 hour |
| `No audio being transmitted`           | Check that call is active and microphone is working          |
| Script hangs on `await runner.run()`   | This is expected; use Ctrl+C to gracefully exit              |
