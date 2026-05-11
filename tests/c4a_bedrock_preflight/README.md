# C4a — Bedrock Preflight

Validates AWS Bedrock credentials and model configuration before running the full speech-to-speech pipeline.

> **Purpose:** Quick validation that Bedrock is accessible and the configured model (Nova Sonic, Nova Lite, etc.) is available and functional.

## Prerequisites

1. **AWS Credentials** — Configure via one of:
   - `AWS_PROFILE=vonage-dev` environment variable (recommended)
   - `~/.aws/credentials` with profile configuration
   - `AWS_ACCESS_KEY_ID` + `AWS_SECRET_ACCESS_KEY` environment variables
2. **AWS Region** — Bedrock access in `us-east-1` (primary Bedrock region)
3. **Model Access** — Amazon Nova Lite model (`amazon.nova-lite-v1:0`) enabled on your AWS account
4. **Python 3.14+** with venv support

## Run Test

### Quick Start (from repo root)

```bash
# Navigate to test directory
cd tests/c4a_bedrock_preflight

# Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies (note: skips Pipecat onnxruntime conflict)
pip install 'boto3>=1.34.0' 'loguru>=0.7.0' 'python-dotenv>=1.2.2' 'vonage>=4.8.0' 'websockets>=15.0.0'

# Run preflight validation
python test_bedrock.py
```

### With AWS Profile

If using named AWS profile (recommended):

```bash
AWS_PROFILE=vonage-dev python test_bedrock.py
```

### Docker

```bash
cd /path/to/repo
docker compose run --rm c4a-bedrock-preflight
```

## Expected Output

### Success Case

When all validations pass:

```
✓ Using AWS profile: vonage-dev (region: us-east-1)
✓ Bedrock client initialised
✓ Model access verified: amazon.nova-lite-v1:0

Sending test prompt: "Say hello in exactly one sentence."
✓ Response received:
  Hello there, how are you doing today?

Test C4a PASSED ✓
```

**Key indicators:**

- AWS profile auto-detected
- Bedrock client successfully created
- Model availability confirmed
- Inference executed and returned response
- Exit code: `0`

## Test Flow

### 1. AWS Profile Resolution

C4a detects and validates AWS credentials from (in order):

- `AWS_PROFILE` environment variable (e.g., `vonage-dev`)
- Explicit `AWS_ACCESS_KEY_ID` + `AWS_SECRET_ACCESS_KEY`
- boto3 default credential chain (~/.aws/credentials)

### 2. Bedrock Client Initialization

Creates boto3 Bedrock client using detected credentials and `us-east-1` region

### 3. Model Access Verification

Tests access to `amazon.nova-lite-v1:0` (Nova Lite for quick validation)

- Confirms model is available in your region
- Verifies IAM permissions allow `bedrock:InvokeModel`

### 4. Inference Test

Runs minimal text-only invocation:

- Prompt: "Say hello in exactly one sentence."
- Validates response format and content
- Confirms model latency is acceptable

## What Gets Validated

| Check                | Purpose                          | Success Indicator              |
| -------------------- | -------------------------------- | ------------------------------ |
| AWS Credentials      | Authentication source resolved   | Profile name or auto-detected  |
| Bedrock Connectivity | API accessibility                | Client initialization succeeds |
| Model Availability   | Nova Lite model exists in region | Model ID accepted by Bedrock   |
| IAM Permissions      | User can invoke model            | No Access Denied errors        |
| Model Inference      | Actual model execution           | Response returned in <5s       |
| Response Format      | Model output validity            | Valid text response received   |

**Success:** All checks pass → Ready for C4b speech-to-speech integration test

## Troubleshooting

| Error                                          | Root Cause                          | Solution                                                                                                                              |
| ---------------------------------------------- | ----------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------- |
| `Unable to locate credentials`                 | No AWS credentials found            | Set `AWS_PROFILE` or configure `~/.aws/credentials`                                                                                   |
| `InvalidAction: User: ... is not authorized`   | Missing IAM permissions             | Grant `bedrock:InvokeModel` permission for user/role                                                                                  |
| `AccessDeniedException`                        | Region access denied                | Switch to `us-east-1` (primary Bedrock region)                                                                                        |
| `ValidationException: Unknown model`           | Model ID incorrect or not available | Verify `amazon.nova-lite-v1:0` exists in your region                                                                                  |
| `ModuleNotFoundError: No module named 'boto3'` | Missing dependencies                | Run: `pip install 'boto3>=1.34.0'`                                                                                                    |
| `onnxruntime~=1.23.2` conflict                 | Pipecat dependency issue            | Skip Pipecat, install only: `pip install 'boto3>=1.34.0' 'loguru>=0.7.0' 'python-dotenv>=1.2.2' 'vonage>=4.8.0' 'websockets>=15.0.0'` |
| `Connection timeout`                           | Network/firewall issue              | Verify AWS API endpoint is reachable (`telnet bedrock.us-east-1.amazonaws.com 443`)                                                   |

## Next Steps

Once C4a **PASSES**:

- ✅ AWS infrastructure validated
- ✅ Bedrock credentials confirmed
- ✅ Model access working
- **→ Proceed to C4b:** Speech-to-speech integration test with Nova Sonic
