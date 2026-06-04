# c8b_runtime_bargein_disconnect

## Goal

Validate barge-in and abrupt disconnect behavior in runtime mode.

## Scope

- User interrupts active response
- Mid-response hangup
- Unexpected socket close

## Pass Criteria

- Barge-in does not deadlock the pipeline.
- Disconnects release resources and end tasks.
- No persistent stuck session state.
