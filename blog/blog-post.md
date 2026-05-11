# Vonage Audio Serializer + AWS Bedrock Voice Agent

This repository implements a speech-to-speech AI voice agent using:

- **Vonage Audio Serializer Transport** — WebSocket-based audio streaming optimized for audio-only Pipecat pipelines
- **Pipecat Framework** — Orchestration layer for speech-to-speech processing
- **AWS Bedrock Nova Sonic** — LLM for conversational voice intelligence
- **AWS AgentCore** (optional) — Bootstrap layer for advanced agent capabilities (knowledge bases, tools, planning)

The architecture flows: **Vonage Voice Call → Audio Serializer (WebSocket) → Pipecat Pipeline → Bedrock Nova Sonic → Response back to Call**

For setup and run instructions, see the root `README.md` and test-stage READMEs under `tests/`.

**Key Design Decision:** This application uses the **Vonage Audio Serializer** (not Video Connector) because:

- Application is audio-only (no video processing required)
- Audio Serializer is optimized for speech-to-speech pipelines
- Simpler integration, lower latency, fewer dependencies than WebRTC-based Video Connector
- Aligns with [official Vonage Pipecat guidance](https://developer.vonage.com/en/video/guides/vonage-pipecat-serializer-overview)
