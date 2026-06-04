# c9_runtime_session_correlation

## Goal

Prove one correlation key can trace a call across Vonage webhook, Lambda logs, and runtime logs.

## Scope

- Session ID selection strategy
- Log field consistency
- Correlation lookup workflow

## Pass Criteria

- One call can be traced end-to-end with a single identifier.
- Correlation fields are documented and consistent.
