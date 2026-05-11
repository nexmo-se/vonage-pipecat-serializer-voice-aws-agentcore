# C5 — AgentCore Runtime

Tests optional AWS Bedrock AgentCore bootstrap for initializing agent behavior (knowledge bases, tools, planning).

> **Purpose:** AgentCore is an optional layer that can be used to prime the voice agent with specialized instructions, knowledge bases, and tool integrations at runtime. This test validates that the AgentCore invocation pathway works.

## Prerequisites

1. AWS credentials configured with AgentCore permissions
2. AgentCore runtime deployed and accessible
3. `AGENTCORE_AGENT_ARN` set in `.env` (ARN of your AgentCore runtime)
4. IAM permissions for `bedrock-agent-runtime:InvokeAgent`

## Run commands

### Native

```bash
cd tests/c5_agentcore_runtime
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python test_agentcore.py
```

### Docker

```bash
docker compose run --rm c5-agentcore-runtime
```

## Expected output

Successful AgentCore invocation produces:

```
Bedrock AgentCore Runtime Test
Agent ARN: <AGENTCORE_AGENT_ARN>
✓ AgentCore runtime initialized
✓ Agent invocation succeeded
Response: <agent output>
C5 PASSED ✓
```

## What's happening

1. **Credentials Check** — Verifies AWS credentials have AgentCore access
2. **Runtime Verification** — Confirms AgentCore runtime exists and is accessible
3. **Agent Invocation** — Sends test request to AgentCore runtime
4. **Response Handling** — Parses and displays agent response

## Test findings

- ✅ AWS Bedrock AgentCore runtime accessibility
- ✅ IAM permissions for agent invocation
- ✅ Agent request payload formatting
- ✅ Response parsing and handling
- ✅ Integration with the voice pipeline bootstrap

## Troubleshooting

| Issue                           | Solution                                                   |
| ------------------------------- | ---------------------------------------------------------- |
| `Agent ARN is empty or invalid` | Set `AGENTCORE_AGENT_ARN` in `.env` with valid runtime     |
| `AccessDenied to AgentCore`     | Check IAM policy includes `bedrock-agent-runtime` access   |
| `Runtime not found`             | Verify ARN and region match your AgentCore deployment      |
| `ValidationException`           | Check agent request payload format matches expected schema |
| `Import errors`                 | Run `pip install -r requirements.txt`                      |

## Notes

- AgentCore is **optional** — the voice agent works without it (C1-C4b)
- AgentCore allows you to add knowledge bases, tools, and planning capabilities
- Use C5 after C4b if you want to enable advanced agent features
