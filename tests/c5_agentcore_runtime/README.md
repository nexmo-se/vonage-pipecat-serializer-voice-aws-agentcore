# C5 — AgentCore Runtime

## Prerequisites

- AWS credentials with AgentCore permissions
- Runtime ARN available after deployment

## Run commands

```bash
cd tests/c5_agentcore_runtime
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python test_agentcore.py
```

## Expected output

- Runtime invoke succeeds
- Response payload from AgentCore is printed

## Troubleshooting

- ARN errors: confirm runtime exists in the configured region
- Permission failures: verify IAM policy for AgentCore invoke APIs
