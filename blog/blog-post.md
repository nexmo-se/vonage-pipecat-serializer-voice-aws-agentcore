# Serializer + Voice Migration Notes

This repository now uses a **serializer + voice** architecture:

- Vonage Voice Linux SDK handles call connectivity
- Vonage Pipecat serializer handles media events
- AWS Bedrock Nova Sonic handles live voice intelligence
- AWS AgentCore remains an optional bootstrap source

For current setup and run instructions, use the root `README.md` and test-stage READMEs under `tests/`.
