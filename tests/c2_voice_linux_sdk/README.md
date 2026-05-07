# C2 — Voice Linux SDK Connectivity

## Prerequisites

- Complete C1 (`VONAGE_CALL_ID` available)
- Linux runtime or Docker

## Run commands

Native:

```bash
cd tests/c2_voice_linux_sdk
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python test_voice_linux_sdk.py
```

Docker:

```bash
cd /home/runner/work/vonage-pipecat-serializer-voice-aws-agentcore/vonage-pipecat-serializer-voice-aws-agentcore
docker compose run --rm c2-voice-linux-sdk
```

## Expected output

- `✓ Linux SDK bridge connected`
- `✓ Linux SDK bridge disconnected`
- `C2 PASSED ✓`

## Troubleshooting

- Connection timeout: validate `VONAGE_CALL_ID`
- Missing native libs: use Docker flow on non-Linux systems
