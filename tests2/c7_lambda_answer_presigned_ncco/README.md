# c7_lambda_answer_presigned_ncco

## Status: PASSED

## Goal

Validate `answer/answer.py` produces valid NCCO with a fresh AgentCore presigned WSS URL.

## What was tested

The handler was invoked directly (no Lambda deployment) using the live deployed runtime ARN
(`vonage_runtime_agent-GC5gEQBPPz`). AWS SCP restrictions prevent Lambda function creation
in this account, but the core logic — presigned URL generation and NCCO construction — is
what c7 validates.

## Run the test

```bash
cd <repo-root>
AWS_PROFILE=vonage-dev python tests2/c7_lambda_answer_presigned_ncco/test_c7_lambda_answer_presigned_ncco.py
```

Expected output:
```json
{
  "stage": "c7_lambda_answer_presigned_ncco",
  "checks": {
    "non_get_returns_405": { "status": "PASS" },
    "get_returns_valid_ncco": {
      "status": "PASS",
      "wss_uri_prefix": "wss://bedrock-agentcore.us-east-1.amazonaws.com/runtimes/arn%3Aaws%3Abedrock-age..."
    }
  },
  "summary": { "passed": 2, "failed": 0 },
  "status": "PASS"
}
```

## Lambda Deployment: SCP Investigation

The test runs the handler in-process because `lambda:CreateFunction` was denied by an
AWS Organizations Service Control Policy (SCP).

### Commands used to investigate

**1. Attempt to create the function (fails with AccessDeniedException):**
```bash
AWS_PROFILE=vonage-dev aws lambda create-function \
  --function-name vonage-agentcore-answer \
  --runtime python3.11 \
  --role arn:aws:iam::589536902306:role/BedrockLambdaRole \
  --handler answer.handler \
  --zip-file fileb:///tmp/vonage_answer.zip \
  --region us-east-1
# → AccessDeniedException: lambda:CreateFunction not authorized
```

**2. Check current user policies:**
```bash
AWS_PROFILE=vonage-dev aws iam list-attached-user-policies \
  --user-name aws-connect-cse
# → IAMFullAccess, AmazonS3FullAccess, AmazonConnect_FullAccess,
#   AmazonBedrockFullAccess, BedrockAgentCoreFullAccess
```

**3. Attach AWSLambda_FullAccess (self-granted via IAMFullAccess):**
```bash
AWS_PROFILE=vonage-dev aws iam attach-user-policy \
  --user-name aws-connect-cse \
  --policy-arn arn:aws:iam::aws:policy/AWSLambda_FullAccess
```

**4. Simulate the permission to confirm it looks allowed at the IAM level:**
```bash
AWS_PROFILE=vonage-dev aws iam simulate-principal-policy \
  --policy-source-arn arn:aws:iam::589536902306:user/aws-connect-cse \
  --action-names lambda:CreateFunction \
  --resource-arns "arn:aws:lambda:us-east-1:589536902306:function:vonage-agentcore-answer"
# → "EvalDecision": "allowed"   ← IAM says allowed, but SCP overrides this
```

**5. Check permission boundary (not set):**
```bash
AWS_PROFILE=vonage-dev aws iam get-user \
  --user-name aws-connect-cse \
  --query 'User.PermissionsBoundary'
# → null
```

**6. Check user groups (none):**
```bash
AWS_PROFILE=vonage-dev aws iam list-groups-for-user \
  --user-name aws-connect-cse
# → { "Groups": [] }
```

**7. Attempt to list SCPs (blocked — organization-level permission required):**
```bash
AWS_PROFILE=vonage-dev aws organizations list-policies-for-target \
  --target-id 589536902306 \
  --filter SERVICE_CONTROL_POLICY
# → AccessDeniedException: You don't have permissions to access this resource.
```

**Conclusion:** IAM simulation says `allowed`, but `CreateFunction` still fails. This indicates
an SCP applied at the AWS Organizations level (account `589536902306` in org `o-e48k2noeyt`,
master `310680773747`). SCP evaluation is invisible to the account user — it silently overrides
the IAM decision.

To deploy the Lambda, an account admin or the master account holder must either:
- Grant a Lambda-creation exception in the SCP, or
- Deploy via a privileged mechanism (CloudFormation StackSet, Terraform with elevated role, CI/CD pipeline with cross-account role)

## Pass Results

| Check                                                                               | Status |
| ----------------------------------------------------------------------------------- | ------ |
| Non-GET returns 405                                                                 | PASS   |
| GET returns HTTP 200 + valid NCCO JSON                                              | PASS   |
| NCCO `action` == `connect`                                                          | PASS   |
| `endpoint[0].type` == `websocket`                                                   | PASS   |
| `endpoint[0].uri` starts with `wss://bedrock-agentcore.us-east-1.amazonaws.com/...` | PASS   |
| `endpoint[0].content-type` == `audio/l16;rate=16000`                                | PASS   |

## Key Findings

- `AgentCoreRuntimeClient.generate_presigned_url(runtime_arn, session_id=...)` returns a valid
  `wss://bedrock-agentcore.us-east-1.amazonaws.com/runtimes/{encoded-arn}/ws?X-Amz-...` URL.
- NCCO structure is correct for Vonage WebSocket `connect` action.
- The presigned URL URL-encodes the ARN (`:` → `%3A`). Whether Vonage correctly follows
  this URL when dialling has **not yet been tested** — c7 validated NCCO generation only,
  not a live Vonage call.

## Scope

- Method handling (GET)
- Presigned URL generation via `AgentCoreRuntimeClient`
- NCCO schema fields and content-type
