# c7_lambda_answer_presigned_ncco

## Goal

Validate Lambda /answer produces NCCO with a fresh AgentCore presigned WSS URL.

## Scope

- Method handling (GET)
- Presigned URL generation call
- NCCO schema fields and content-type

## Pass Criteria

- Lambda returns HTTP 200 with valid NCCO JSON.
- NCCO endpoint URI is a presigned AgentCore WSS URL.
- Error paths return controlled responses.
