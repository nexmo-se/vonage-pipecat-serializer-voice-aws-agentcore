# C2 — Audio Serializer Connectivity

Validates Vonage Audio Serializer WebSocket bridge connectivity to the active voice call session.

> **Note:** This test verifies the Audio Serializer transport layer before full Pipecat pipeline integration (C3). The Vonage Audio Serializer provides WebSocket-based audio streaming for audio-only Pipecat pipelines, per [official Vonage documentation](https://developer.vonage.com/en/video/guides/vonage-pipecat-serializer-overview).

## Prerequisites

1. **C1 must be completed** — You must have a valid `VONAGE_CALL_ID` in your root `.env` file
2. **Docker or Python 3.13+** — Required for WebSocket connectivity testing
3. **Valid Vonage credentials** — `.env` must have `VONAGE_APPLICATION_ID` and `VONAGE_PRIVATE_KEY`

## Run Instructions

### Quick Start (native Python)

```bash
cd tests/c2_voice_linux_sdk
python3 -m venv .venv
source .venv/bin/activate
pip install -q -r requirements.txt
python test_voice_linux_sdk.py
```

### Docker (recommended)

```bash
cd /path/to/vonage-pipecat-serializer-voice-aws-agentcore
docker compose run --rm c2-audio-serializer
```

## Expected Output

Successful C2 test produces:

```
Testing Audio Serializer WebSocket bridge for call 1_MX4zZjI4NTlhYy01OWU4LTQ2YjEtODFiOS1hZjE2NWFhZTVkNjN-fjE3NzgxODEyNTQwNDF-OE14c0ZjaFl5N…
✓ Token generated (860 chars)
✓ Vonage credentials validated
✓ Call ID is valid (1_MX4zZjI4NTlhYy01OWU4LTQ2YjEtODFiOS1hZjE2NWFhZTVkNjN-fjE3NzgxODEyNTQwNDF-OE14c0ZjaFl5N...)
✓ Audio Serializer bridge is ready for WebSocket connection

Audio Serializer transport configuration:
  - Application ID: 3f2859ac...
  - CCredentials Validation** — Verifies your Vonage application ID and private key work
2. **Token Generation** — Creates a publisher JWT token for WebSocket authentication
3. **Call ID Validation** — Confirms the voice call session ID is valid and reusable
4. **Audio Format Configuration** — Displays PCM audio settings for the serializer (16-bit, 16kHz, mono)
5. **Bridge Readiness Check** — Verifies Audio Serializer transport is ready for WebSocket connection

This test prepares the foundation for C3 (Pipecat Echo Bot), which will establish the actual WebSocket connection and process audio through the Pipecat pipeline.
C2 PASSED ✓
```

### What This Test Does

1. **Token Generation** — Creates a publisher token using your Vonage credentials
2. **WebSocket Connection** — Audio Serializer transport establishes WebSocket bridge to Vonage
3. **Connection Validation** — Verifies handshake and audio stream readiness
4. **Audio Format Configuration** — Displays PCM audio settings for the serializer (16-bit, 16kHz, mono)
5. **Bridge Readiness Check** — Verifies Audio Serializer transport is ready for WebSocket connection

This test prepares the foundation for C3 (Pipecat Echo Bot), which will establish the actual WebSocket connection and process audio through the Pipecat pipeline.

## Validation Checks

- ✅ Vonage API authentication (token generation successful)
- ✅ Valid Vonage credentials (application ID + private key)
- ✅ Call ID validity and reusability
- ✅ Audio format configuration (PCM 16-bit, 16000 Hz, mono)
- ✅ Publisher JWT token created
- ✅ Audio Serializer transport ready for WebSocket bridge

## Troubleshooting

| Issue                                                 | Solution                                                               |
| ----------------------------------------------------- | ---------------------------------------------------------------------- |
| `ERROR: Missing env vars: VONAGE_CALL_ID`             | Run C1 first; call ID should be auto-saved to `.env`                   |
| `ERROR: Private key not found`                        | Ensure `VONAGE_PRIVATE_KEY` in `.env` points to valid key file         |
| `ModuleNotFoundError: No module named 'vonage'`       | Run `pip install -r requirements.txt`                                  |
| `ModuleNotFoundError: No module named 'vonage_video'` | Vonage package issue; try `pip install --upgrade vonage`               |
| `ERROR: Missing dependency`                           | All requirements installed? Try `pip install -q -r requirements.txt`   |
| `docker: command not found`                           | Install Docker Desktop: https://www.docker.com/products/docker-desktop |

## Environment Variables

From root `.env`:

- `VONAGE_APPLICATION_ID` — Your Vonage application ID
- `VONAGE_PRIVATE_KEY` — Path to your private key file
- `VONAGE_CALL_ID` — Session ID created by C1 (auto-saved to `.env`)

## Next Steps

After C2 passes ✅, proceed to **C3 (Pipecat Echo Bot)** to test the full serializer pipeline:

```bash
cd ../c3_pipecat_serializer && python serializer_echo_bot.py
```

or with Docker:

```bash
cd /path/to/repo && docker compose run --rm c3-pipecat-serializer
```

**Sequential Testing Path:**

- ✅ **C1** — Voice call bootstrap (generates VONAGE_CALL_ID)
- ✅ **C2** — Audio Serializer WebSocket connectivity
- **C3** — Pipecat echo bot (validates pipeline)
- **C4a** — AWS Bedrock preflight check
- **C4b** — Bedrock Nova Sonic integration
- **C5** — AgentCore runtime (optional)
- **app/** — Full integration test
