# C4b — Bedrock Nova Sonic + Serializer

## Prerequisites

- Complete C1–C4a
- Linux runtime or Docker

## Run commands

```bash
cd tests/c4b_bedrock_nova_sonic_serializer
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python test_bedrock.py
python test_integration.py
```

Optional live echo:

```bash
python bedrock_echo_agent.py
```

## Expected output

- Bedrock checks pass
- Nova Sonic integration path initializes without errors

## Troubleshooting

- Initialization failures: verify `BEDROCK_MODEL_ID` and region pairing
- Audio path issues: rerun C2/C3 to verify call media bridge health
