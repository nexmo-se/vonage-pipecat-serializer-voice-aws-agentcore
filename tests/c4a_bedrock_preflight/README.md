# C4a — Bedrock Preflight

Validates AWS Bedrock credentials and model configuration before running the full speech-to-speech pipeline.

> **Purpose:** Quick validation that Bedrock is accessible and the configured model (Nova Sonic, Nova Lite, etc.) is available and functional.

## Prerequisites

1. AWS credentials configured (`AWS_PROFILE` or AWS environment variables)
2. `AWS_REGION` set in `.env` (e.g., `us-east-1`)
3. `BEDROCK_MODEL_ID` set in `.env` (e.g., `us.anthropic.claude-3-5-sonnet-20241022-v2:0`)
4. Bedrock model access enabled on your AWS account

## Run commands

### Native

```bash
cd tests/c4a_bedrock_preflight
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python test_bedrock.py
python test_integration.py
```

### Docker

```bash
docker compose run --rm c4a-bedrock-preflight
```

## Expected output

Successful preflight produces:

```
AWS Bedrock Preflight Check
✓ Bedrock client initialized
✓ Model access verified: us.anthropic.claude-3-5-sonnet-20241022-v2:0
✓ Bedrock integration module loads correctly
C4a PASSED ✓
```

## What's happening

1. **AWS Credentials Check** — Verifies AWS credentials are available and valid
2. **Bedrock Model Verification** — Confirms the configured model exists and is accessible
3. **Quick Inference Test** — Runs a minimal text-only invocation to verify model responsiveness
4. **Integration Module Load** — Ensures the Bedrock+Serializer integration code loads without errors

## Test findings

- ✅ AWS credentials availability and validity
- ✅ Bedrock API accessibility from your environment
- ✅ Configured model availability and permissions
- ✅ Model invocation payload format correctness
- ✅ Integration module architecture

## Troubleshooting

| Issue                          | Solution                                                          |
| ------------------------------ | ----------------------------------------------------------------- |
| `Unable to locate credentials` | Configure AWS credentials: `aws configure` or set env vars        |
| `Access Denied to Bedrock`     | Check IAM permissions for bedrock:InvokeModel                     |
| `Model not found or invalid`   | Verify `BEDROCK_MODEL_ID` is correct and available in your region |
| `ValidationException`          | Check model supports the region you specified                     |
| `Import errors`                | Run `pip install -r requirements.txt`                             |
