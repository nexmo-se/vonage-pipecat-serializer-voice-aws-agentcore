# C1 — Voice Call Bootstrap

Bootstraps a Vonage Voice API session and generates a call ID token for use in subsequent test stages (C2-C5).

## Prerequisites

1. **Root `.env` file** with valid Vonage credentials:
   - `VONAGE_APPLICATION_ID` — Your Vonage Voice API application ID
   - `VONAGE_PRIVATE_KEY` — Path to your application's private key file (default: `private.key` at repo root)

2. **Python 3.13+** (verify with `python3 --version`)

## Run Instructions

### Quick Start (native Python)

```bash
cd tests/c1_voice_call_bootstrap
python3 -m venv .venv
source .venv/bin/activate
pip install -q -r requirements.txt
python test_voice_bootstrap.py
```

### From Repository Root

```bash
cd tests/c1_voice_call_bootstrap && python3 -m venv .venv && source .venv/bin/activate && pip install -q -r requirements.txt && python test_voice_bootstrap.py
```

## Expected output

Successful C1 test generates:

```
Creating a new Vonage session id for voice serializer tests …
✓ Saved VONAGE_CALL_ID=1_MX4zZjI4NTlhYy01OWU4LTQ2YjEtODFiOS1hZjE2NWFhZTVkNjN-fjE... to /path/to/.env

Call bootstrap output
================================================
Application ID: 3f2859ac-59e8-46b1-81b9-af165aae5d63
Call ID:        1_MX4zZjI4NTlhYy01OWU4LTQ2YjEtODFiOS1hZjE2NWFhZTVkNjN-fjE3NzgxOD...
Token:          eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9...
================================================
C1 PASSED ✓
```

### What This Test Does

1. **Credentials validation**: Verifies your Vonage application ID and private key
2. **Voice session creation**: Creates a new Vonage Voice API session
3. **Call ID generation**: Generates a unique call ID for the voice call
4. **Token creation**: Creates a publisher token (valid 24 hours) for WebSocket authentication
5. **.env persistence**: Automatically saves `VONAGE_CALL_ID` to your root `.env` for downstream tests

## Validation Checks

- ✅ Valid Vonage credentials (application ID + private key)
- ✅ Successful Voice API authentication
- ✅ Session created with unique call ID
- ✅ Publisher token generated
- ✅ `.env` file updated with `VONAGE_CALL_ID`

## Troubleshooting

| Issue                                                                | Solution                                                        |
| -------------------------------------------------------------------- | --------------------------------------------------------------- |
| `ModuleNotFoundError: No module named 'vonage'`                      | Run `pip install -r requirements.txt`                           |
| `Private key file not found: private.key`                            | Ensure `VONAGE_PRIVATE_KEY` points to valid key file in `.env`  |
| `ERROR: Invalid environment missing env vars: VONAGE_APPLICATION_ID` | Set `VONAGE_APPLICATION_ID` in root `.env`                      |
| Auth failures / 401 error                                            | Verify application ID and private key match in Vonage Dashboard |
| `command not found: python`                                          | Use `python3` or `/opt/homebrew/bin/python3` (macOS)            |

## Next Steps

After C1 passes ✅, proceed to **C2 (Audio Serializer Connectivity)** to validate WebSocket bridge:

```bash
cd ../c2_voice_linux_sdk && python test_voice_linux_sdk.py
```

or with Docker:

```bash
cd /path/to/repo && docker compose run --rm c2-audio-serializer
```

**Sequential Testing Path:**

- ✅ **C1** — Voice call bootstrap (generates VONAGE_CALL_ID)
- **C2** — Audio Serializer WebSocket connectivity
- **C3** — Pipecat echo bot
- **C4a** — AWS Bedrock preflight check
- **C4b** — Bedrock Nova Sonic integration
- **C5** — AgentCore runtime (optional)
- **app/** — Full integration test
