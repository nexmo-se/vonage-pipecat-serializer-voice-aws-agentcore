# c10_runtime_expiry_and_retry

## Goal

Validate presigned URL expiry behavior and retry/recovery flow.

## Scope

- Expired URL connection attempt
- Fresh URL regeneration path
- Recovery after initial failure

## Pass Criteria

- Expired URLs fail predictably.
- Fresh URL setup succeeds immediately after retry.
- Behavior is documented for operations runbooks.
