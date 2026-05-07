# app

## Overview and architecture

`app/` hosts the FastAPI runtime for the serializer + voice agent flow.

- Voice call lifecycle is controlled by `POST /join` and `POST /leave`
- Pipecat serializer pipeline handles audio frame orchestration
- Bedrock Nova Sonic provides voice intelligence
- AgentCore bootstrap is optional and only used when `AGENTCORE_AGENT_ARN` is set

## Prerequisites and setup

- Complete root `.env` setup
- Valid `VONAGE_CALL_ID`
- AWS Bedrock access (Nova Sonic model)

```bash
cd app
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Environment variables

Uses root `.env` values, especially:

- `VONAGE_APPLICATION_ID`
- `VONAGE_PRIVATE_KEY`
- `VONAGE_CALL_ID`
- `AWS_REGION`
- `BEDROCK_MODEL_ID`
- `AGENTCORE_AGENT_ARN` (optional)

## Run instructions

```bash
uvicorn main:app --host 0.0.0.0 --port 8000
```

Docker:

```bash
cd ..
docker compose --profile app up --build app
```

## Test instructions

Quick runtime checks:

```bash
curl http://localhost:8000/
curl http://localhost:8000/status
```

## Validation steps

```bash
curl -X POST http://localhost:8000/join -H "Content-Type: application/json" -d '{"call_id":"'$VONAGE_CALL_ID'"}'
curl -X POST http://localhost:8000/leave
```

Expected:

- `/status` shows `running: true` after join
- WebSocket `/ws` emits call/media lifecycle events

## Production notes

- Deploy on Linux-based hosts/containers.
- Use managed secrets and short-lived credentials.
- Monitor Bedrock latency, retries, and call-duration renewal events.
