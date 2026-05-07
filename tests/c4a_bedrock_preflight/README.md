# C4a — Bedrock Preflight

## Prerequisites

- AWS credentials configured
- `AWS_REGION` and `BEDROCK_MODEL_ID` set

## Run commands

```bash
cd tests/c4a_bedrock_preflight
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python test_bedrock.py
python test_integration.py
```

## Expected output

- Bedrock credential/model checks pass
- Integration check prints success status

## Troubleshooting

- Access denied/model errors: confirm account access to the configured model
- Timeout issues: tune Bedrock timeout env vars
