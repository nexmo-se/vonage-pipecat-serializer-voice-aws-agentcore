# vonage-pipecat-serializer-voice-aws-agentcore

Real-time voice agent using **Vonage Pipecat Serializer + Vonage Voice Linux SDK** with **AWS Bedrock Nova Sonic** and optional **AWS AgentCore bootstrap**.

## Overview and architecture

Runtime path:

```text
Vonage Voice call media
  -> Voice Linux SDK bridge
  -> Pipecat serializer pipeline
  -> AWS Nova Sonic (Bedrock)
  -> Pipecat serializer pipeline
  -> Vonage Voice call media
```

AgentCore remains an optional bootstrap layer used at startup to prime assistant behavior.

## Prerequisites and setup

- Linux host or Docker runtime
- Python 3.13+
- Vonage application credentials and `private.key`
- AWS credentials with Bedrock (and AgentCore if enabled)

Setup:

```bash
cp .env.example .env
# update .env values
```

## Environment variables

Primary variables:

- `VONAGE_APPLICATION_ID`
- `VONAGE_PRIVATE_KEY`
- `VONAGE_CALL_ID`
- `AWS_PROFILE` / `AWS_REGION`
- `BEDROCK_MODEL_ID`
- `AGENTCORE_AGENT_ARN` (optional)
- `PORT`

## Run instructions

### App (Docker)

```bash
docker compose --profile app up --build app
```

### App (native)

```bash
cd app
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000
```

## Test instructions

Run staged tests in order:

1. `tests/c1_voice_call_bootstrap`
2. `tests/c2_voice_linux_sdk`
3. `tests/c3_pipecat_serializer`
4. `tests/c4a_bedrock_preflight`
5. `tests/c4b_bedrock_nova_sonic_serializer`
6. `tests/c5_agentcore_runtime`

See each subfolder README for prerequisites, exact commands, expected output, and troubleshooting.

## Validation steps

```bash
curl http://localhost:8000/
curl http://localhost:8000/status
```

Join/leave API:

```bash
curl -X POST http://localhost:8000/join -H "Content-Type: application/json" -d '{"call_id":"'$VONAGE_CALL_ID'"}'
curl -X POST http://localhost:8000/leave
```

## Production notes

- Use Linux-based runtime for Voice SDK compatibility.
- Prefer IAM roles over static AWS keys.
- Keep credentials/secrets outside repository and container images.
- Tune Bedrock timeout/retry env vars for latency and resilience.
