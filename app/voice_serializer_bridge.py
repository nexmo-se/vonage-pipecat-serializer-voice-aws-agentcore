"""Compatibility shim — no longer used by the main agent.

The production agent (agent.py) now uses FastAPIWebsocketTransport +
VonageFrameSerializer directly, which is the correct approach for Vonage
Voice API WebSocket calls.

The VonageAudioSerializerTransport loaded here was part of an earlier
Video SDK / Video Connector approach and is not needed for Voice API calls.
This file is retained for reference only.

Reference: https://developer.vonage.com/en/video/guides/vonage-pipecat-serializer-overview
"""

from __future__ import annotations
