# c8_runtime_end_to_end_single_call

## Goal

Run a full single-call flow: Vonage -> Lambda /answer -> AgentCore Runtime /ws -> Pipecat/Nova.

## Scope

- Call setup and connect
- Greeting and initial turn
- Two-way audio exchange
- Normal call teardown

## Pass Criteria

- Caller hears greeting and receives responses.
- No critical runtime errors in Lambda or runtime logs.
- Connection lifecycle events complete cleanly.
