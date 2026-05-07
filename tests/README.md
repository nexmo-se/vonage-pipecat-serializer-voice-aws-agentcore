# tests

## Overview and architecture

This suite validates serializer + voice components in isolated stages, then as an integrated chain.

## Execution order

1. `c1_voice_call_bootstrap`
2. `c2_voice_linux_sdk`
3. `c3_pipecat_serializer`
4. `c4a_bedrock_preflight`
5. `c4b_bedrock_nova_sonic_serializer`
6. `c5_agentcore_runtime`

Stages are independently runnable and can also be executed sequentially.

## Prerequisites and setup

- Root `.env` configured
- Python 3.13+ or Docker
- `private.key` available at repository root (or matching `.env` path)

## Run instructions

Use each subfolder README for exact commands.

## Validation steps

A successful sequence should leave you with:

- a valid `VONAGE_CALL_ID`
- verified Linux SDK connectivity
- verified serializer echo path
- verified Bedrock preflight and Nova Sonic integration
- verified AgentCore runtime invocation

## Troubleshooting

- Confirm `.env` values are not placeholders.
- Ensure AWS profile/region is available in your shell or mounted in Docker.
- Run each stage standalone first before chaining all stages.
