"""Compatibility layer for the Vonage serializer bridge classes."""

from __future__ import annotations


def load_serializer_bridge_classes():
    """Load bridge classes used by the serializer + voice runtime."""
    from pipecat.transports.vonage.video_connector import (
        VonageVideoConnectorTransport as VoiceSerializerBridge,
        VonageVideoConnectorTransportParams as VoiceSerializerBridgeParams,
    )

    return VoiceSerializerBridge, VoiceSerializerBridgeParams
