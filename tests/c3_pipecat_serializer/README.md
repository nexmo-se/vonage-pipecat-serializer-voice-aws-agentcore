# C3 — Pipecat Serializer Echo

## Prerequisites

- Complete C1 and C2
- Linux runtime or Docker

## Run commands

Native:

```bash
cd tests/c3_pipecat_serializer
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python serializer_echo_bot.py
```

Docker:

```bash
cd /home/runner/work/vonage-pipecat-serializer-voice-aws-agentcore/vonage-pipecat-serializer-voice-aws-agentcore
docker compose run --rm c3-pipecat-serializer
```

## Expected output

- Joined call event appears
- Echo audio round-trip is observable
- Script exits cleanly with Ctrl+C

## Troubleshooting

- No audio: verify microphone permissions and call participation
- Auth errors: rerun C1 to refresh credentials/token path
