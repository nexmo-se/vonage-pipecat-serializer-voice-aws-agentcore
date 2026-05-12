# C5 — AWS Bedrock AgentCore Runtime

**Optional integration test:** Validates AWS Bedrock AgentCore runtime invocation for advanced agent features (knowledge bases, tools, planning).

> **AgentCore is optional** — The voice agent works end-to-end with C1-C4b. Use C5 if you need specialized knowledge bases, tool integrations, or custom planning logic at runtime.

## System Architecture

```
Voice Agent (C4b)
    ↓
Wants to augment behavior with knowledge/tools
    ↓
Invoke AgentCore Runtime (C5)
    ↓
AgentCore runtime processes request
    ↓
Returns specialized response to voice agent
    ↓
Voice agent streams response to caller
```

## Prerequisites Checklist

- [ ] C4b passed (Vonage + Nova Sonic agent working)
- [ ] AWS credentials configured with `bedrock-agent-runtime` permissions
- [ ] AgentCore runtime deployed and accessible in `us-east-1`
- [ ] `AGENTCORE_AGENT_ARN` set in `.env` (ARN of your runtime)
- [ ] Python 3.14+ with shared venv at `tests/c2_voice_linux_sdk/venv`
- [ ] IAM policy includes: `bedrock-agent-runtime:InvokeAgent` action

## Environment Setup

### 1. Verify AWS Credentials

```bash
# Check profile has AgentCore permissions
aws sts get-caller-identity --profile vonage-dev
aws bedrock-agentcore list-agents --region us-east-1 --profile vonage-dev
```

Expected: Returns your AWS account ID and can list agents.

### 2. Set AgentCore Runtime ARN

In `.env` (repo root):

```bash
# AWS Bedrock AgentCore Runtime
AGENTCORE_AGENT_ARN=arn:aws:bedrock-agentcore:us-east-1:<ACCOUNT_ID>:runtime/<AGENT_NAME>-<ID>
```

**To find your ARN:**

```bash
# List all AgentCore runtimes
aws bedrock-agentcore list-agents --region us-east-1 --profile vonage-dev

# Copy the agentRuntimeArn from output
```

### 3. Install Dependencies

```bash
cd tests/c5_agentcore_runtime
source ../c2_voice_linux_sdk/venv/bin/activate
pip install -r requirements.txt
```

## Running the Test

### Phase 1: Validate AgentCore Configuration (No Venv Needed)

```bash
cd tests/c5_agentcore_runtime
source ../c2_voice_linux_sdk/venv/bin/activate
python test_agentcore.py
```

**Expected output:**

```
✓ Using existing runtime: arn:aws:bedrock-agentcore:us-east-1:...
Invoking agent with: "Say hello world"
✓ Agent response:
  "Hello, <input>! AgentCore is working."

Test C5 PASSED ✓
```

**If you see `ERROR: Missing AGENTCORE_AGENT_ARN`:**
- Set the ARN in `.env` before running
- Restart terminal to reload `.env`

---

## What C5 Validates

| Component | Check | Result |
|-----------|-------|--------|
| AWS Credentials | Can access `bedrock-agentcore` service | ✓ Verified |
| IAM Permissions | `bedrock-agent-runtime:InvokeAgent` allowed | ✓ Verified |
| Runtime Accessibility | Runtime ARN is valid and deployed | ✓ Verified |
| Agent Invocation | Can send request and parse response | ✓ Verified |
| Integration Ready | Pathway for voice agent → AgentCore works | ✓ Verified |

---

## How to Use AgentCore with Voice Agent

After C5 passes, you can integrate AgentCore into the C4b voice agent:

### Step 1: Import AgentCore client in bedrock_echo_agent.py

```python
import boto3

agentcore_client = boto3.client("bedrock-agentcore", region_name="us-east-1")
```

### Step 2: Augment agent response with AgentCore

```python
# In your voice pipeline, before sending response:

# Get response from Nova Sonic
response = nova_sonic.get_response(user_input)

# If specialized handling needed, call AgentCore:
agentcore_response = agentcore_client.invoke_agent_runtime(
    agentRuntimeArn=AGENTCORE_AGENT_ARN,
    contentType="application/json",
    accept="application/json",
    payload=json.dumps({"input": response}).encode("utf-8"),
)

# Use augmented response
```

### Step 3: Deploy and test live call

Once integrated, test with live Vonage call to hear AgentCore response.

---

## Troubleshooting

### Configuration Issues

| Symptom | Root Cause | Solution |
|---------|-----------|----------|
| `ERROR: Missing AGENTCORE_AGENT_ARN` | ARN not set in `.env` | Set `AGENTCORE_AGENT_ARN=arn:aws:bedrock-agentcore:...` and reload terminal |
| `Invalid ARN format` | Malformed ARN | Verify format: `arn:aws:bedrock-agentcore:us-east-1:<ACCOUNT>:runtime/<NAME>-<ID>` |
| `.env file not found` | Running from wrong directory | `cd /path/to/repo/root` before running |

### AWS Credentials Issues

| Symptom | Root Cause | Solution |
|---------|-----------|----------|
| `NoCredentialsError` | No AWS credentials configured | Run `aws configure --profile vonage-dev` or set `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY` |
| `AccessDenied` when invoking agent | Missing `bedrock-agent-runtime:InvokeAgent` IAM permission | Contact AWS admin to add permission to IAM role |
| `ProfileNotFound` | Profile name doesn't exist | Verify profile: `aws configure list --profile vonage-dev` |

### AgentCore Runtime Issues

| Symptom | Root Cause | Solution |
|---------|-----------|----------|
| `ResourceNotFound` or 404 | Runtime ARN invalid or runtime deleted | Verify ARN with: `aws bedrock-agentcore list-agents --region us-east-1` |
| `ValidationException` | Payload format incorrect | Check agent expects JSON with `{"input": "..."}` structure |
| `ServiceUnavailable` | AgentCore service temporarily down | Wait 30 seconds, retry test |
| Response is empty or `null` | Agent returned no output | Check agent implementation handles input correctly |

### Dependency Issues

| Symptom | Root Cause | Solution |
|---------|-----------|----------|
| `ModuleNotFoundError: boto3` | Dependency not installed | Run: `pip install -r requirements.txt` |
| `ModuleNotFoundError: bedrock-agentcore` | Package name mismatch | Run: `pip install bedrock-agentcore aioboto3` |

---

## Debugging

**Enable verbose output:**

```bash
cd tests/c5_agentcore_runtime
source ../c2_voice_linux_sdk/venv/bin/activate
python -u test_agentcore.py 2>&1 | tee agentcore_debug.log
```

**Verify runtime exists:**

```bash
aws bedrock-agentcore list-agents \
  --region us-east-1 \
  --profile vonage-dev | python -m json.tool
```

**Check IAM permissions:**

```bash
# Verify InvokeAgent permission
aws iam get-user-policy \
  --user-name your-user \
  --policy-name your-policy \
  --profile vonage-dev | grep bedrock-agent-runtime
```

---

## Next Steps

- **Continue to app/** — Full production deployment with Docker and all 5 components
- **Integrate AgentCore** — Add AgentCore augmentation to live voice pipeline
- **Deploy to production** — Use Dockerfile and docker-compose for full stack

## Notes

- **AgentCore is optional** — C1-C4b provide complete speech-to-speech agent
- **Requires pre-deployed runtime** — Use `agentcore configure` + `agentcore deploy` to create a runtime first
- **Region-specific** — AgentCore runtime must be in `us-east-1` (same as Nova Sonic)
- **Invocation cost** — Each AgentCore invocation incurs API charges; use sparingly in production
