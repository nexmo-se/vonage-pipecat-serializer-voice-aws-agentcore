"""Compatibility layer for the Vonage Pipecat Audio Serializer bridge classes.

Uses the Vonage Audio Serializer Transport which is Pipecat's serializer for
Vonage Voice API sessions. Provides WebSocket-based audio streaming for audio-only
pipelines connected to Vonage Voice API.

Reference: https://developer.vonage.com/en/video/guides/vonage-pipecat-serializer-overview
"""

from __future__ import annotations


def load_serializer_bridge_classes():
    """Load bridge classes used by the Vonage Audio Serializer + voice runtime.
    
    The Vonage Audio Serializer Transport provides WebSocket-based audio streaming
    for audio-only Pipecat pipelines connected to Vonage Voice API.
    """
    from pipecat.transports.vonage.audio_serializer import (
        VonageAudioSerializerTransport as VoiceSerializerBridge,
        VonageAudioSerializerTransportParams as VoiceSerializerBridgeParams,
    )

    return VoiceSerializerBridge, VoiceSerializerBridgeParams
