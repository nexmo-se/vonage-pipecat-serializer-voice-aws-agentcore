# tests2

Second test lane for production-path validation before modifying the main app.

## Purpose

Validate unknowns for Lambda Function URL + AgentCore Runtime integration while keeping the current local app flow unchanged.

## Execution Order (Gate-Driven)

> **Reference:** `c5_pipecat_agentcore_ws/` is not a test stage — it contains the upstream
> `pipecat-ai/pipecat-examples/aws-agentcore` source as a reference baseline for c6.

1. **c6_agentcore_ws_serializer_smoke** ✅ PASSED — VonageFrameSerializer + FastAPIWebsocketTransport confirmed inside AgentCore Runtime
2. c7_lambda_answer_presigned_ncco *(requires `answer/answer.py` to be built first)*
3. c8_runtime_end_to_end_single_call *(requires `runtime/agent.py` to be built first)*
4. c8b_runtime_bargein_disconnect
5. c9_runtime_session_correlation
6. c10_runtime_expiry_and_retry
7. c11_runtime_concurrency
8. c13_security_and_compliance
9. c14_quota_and_region_matrix

## Promotion Rule

c6 passed. Build `runtime/agent.py` and `answer/answer.py` (see root `README.md`), then run c7 → c8 onward.

## Common Artifacts Per Stage

- README.md (goal, scope, run steps, expected results)
- requirements.txt (if needed)
- test\_\*.py (or runner script)
- fixtures/ (optional sample payloads)
- expected/ (optional golden outputs)

## Runner

Use the stage runner to execute in gate order and stop at first failure.

```bash
# List stages
python tests2/run_all.py --list

# Run all stages from c6
python tests2/run_all.py

# Resume from a specific stage
python tests2/run_all.py --start-at c8_runtime_end_to_end_single_call
```

## Exit Criteria for tests2

- Serializer + transport confirmed in AgentCore Runtime on port 8080.
- Lambda /answer returns valid NCCO with presigned WSS URLs.
- Single-call and multi-call paths are stable.
- Session correlation is traceable across Vonage, Lambda, and runtime logs.
- Expiry/retry behavior and security checks are documented and validated.
