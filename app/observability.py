#!/usr/bin/env python3
"""Observability module — OpenTelemetry + Prometheus metrics.

Provides:
  - Prometheus metrics export for monitoring
  - OpenTelemetry tracer for distributed tracing
  - Call-level metrics (duration, error counts, latency)
  - Span tracking for debugging
"""

from __future__ import annotations

import time
from contextlib import asynccontextmanager
from typing import Any

from opentelemetry import metrics, trace
from opentelemetry.exporter.prometheus import PrometheusMetricReader
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.trace import TracerProvider
from prometheus_client import REGISTRY, Counter, Histogram

# ── Prometheus Metrics ────────────────────────────────────────────

# Call lifecycle metrics
call_count = Counter(
    "voice_calls_total",
    "Total number of voice calls",
    ["status"],  # "connected", "completed", "failed"
)

call_duration_seconds = Histogram(
    "voice_call_duration_seconds",
    "Voice call duration in seconds",
    buckets=(1, 5, 10, 30, 60, 120, 300, 600),  # Up to 10 minutes
)

call_errors_total = Counter(
    "voice_call_errors_total",
    "Total call errors by type",
    ["error_type"],
)

# LLM/Bedrock metrics
bedrock_latency_ms = Histogram(
    "bedrock_latency_ms",
    "AWS Bedrock invocation latency in milliseconds",
    buckets=(10, 50, 100, 200, 500, 1000, 2000, 5000),
)

bedrock_errors_total = Counter(
    "bedrock_errors_total",
    "Total Bedrock service errors",
)

agentcore_latency_ms = Histogram(
    "agentcore_latency_ms",
    "AWS Bedrock AgentCore invocation latency in milliseconds",
    buckets=(10, 50, 100, 200, 500, 1000, 2000),
)

agentcore_validation_failures = Counter(
    "agentcore_validation_failures_total",
    "AgentCore response validation failures",
    ["failure_reason"],
)

# Frame processing metrics
frames_processed = Counter(
    "voice_frames_processed_total",
    "Total voice frames processed",
    ["direction"],  # "input", "output"
)

pipeline_errors_total = Counter(
    "voice_pipeline_errors_total",
    "Total pipeline processing errors",
)

# ── OpenTelemetry Setup ──────────────────────────────────────────

def init_observability():
    """Initialize OpenTelemetry with Prometheus exporter.
    
    Sets up:
      - Prometheus metrics reader
      - Meter provider
      - Tracer provider (for future distributed tracing)
    
    Returns:
      (tracer, meter) tuple for use in application
    """
    # Prometheus exporter
    prometheus_reader = PrometheusMetricReader(registry=REGISTRY)
    
    # Meter provider with Prometheus exporter
    meter_provider = MeterProvider(metric_readers=[prometheus_reader])
    metrics.set_meter_provider(meter_provider)
    
    # Tracer provider (for OpenTelemetry spans)
    tracer_provider = TracerProvider()
    trace.set_tracer_provider(tracer_provider)
    
    # Get tracer and meter for application use
    tracer = trace.get_tracer(__name__)
    meter = metrics.get_meter(__name__)
    
    return tracer, meter


# Initialize when module is imported
try:
    tracer, meter = init_observability()
except Exception:
    # Fallback if observability fails (don't break app)
    tracer = None
    meter = None


# ── Span Context Manager ──────────────────────────────────────────

@asynccontextmanager
async def trace_span(name: str, attributes: dict[str, Any] | None = None):
    """Context manager for OpenTelemetry span tracking.
    
    Usage:
      async with trace_span("bedrock_invoke", {"model_id": "nova-sonic"}):
          result = await bedrock_invoke(...)
    """
    if tracer is None:
        yield
        return
    
    with tracer.start_as_current_span(name) as span:
        if attributes:
            for key, value in attributes.items():
                try:
                    span.set_attribute(key, value)
                except (TypeError, ValueError):
                    # Skip non-serializable attributes
                    pass
        yield


# ── AgentCore Response Validation ─────────────────────────────────

def validate_agentcore_response(response: str) -> tuple[bool, str | None]:
    """Validate AWS Bedrock AgentCore response structure.
    
    Args:
        response: Raw response string from AgentCore
    
    Returns:
        (is_valid, error_reason): Tuple of validation result and optional error reason
    
    Examples:
        >>> is_valid, error = validate_agentcore_response('{"output": "text"}')
        >>> is_valid
        True
        
        >>> is_valid, error = validate_agentcore_response('invalid json')
        >>> is_valid
        False
        >>> error
        'invalid_json'
    """
    if not response:
        agentcore_validation_failures.labels(failure_reason="empty_response").inc()
        return False, "empty_response"
    
    # Check JSON validity
    import json
    try:
        data = json.loads(response)
    except (json.JSONDecodeError, ValueError):
        agentcore_validation_failures.labels(failure_reason="invalid_json").inc()
        return False, "invalid_json"
    
    # Check response is dict-like
    if not isinstance(data, dict):
        agentcore_validation_failures.labels(failure_reason="not_dict").inc()
        return False, "not_dict"
    
    # Optionally check for required fields (customize based on AgentCore API)
    # For now, just validate it's valid JSON
    
    return True, None


# ── Metrics Recording Helpers ─────────────────────────────────────

def record_call_duration(duration_seconds: float, status: str = "completed"):
    """Record call duration and status metrics.
    
    Args:
        duration_seconds: Call duration in seconds
        status: Call outcome ("completed", "failed", "timeout")
    """
    call_duration_seconds.observe(duration_seconds)
    call_count.labels(status=status).inc()


def record_bedrock_latency(latency_ms: float):
    """Record Bedrock service latency."""
    bedrock_latency_ms.observe(latency_ms)


def record_agentcore_latency(latency_ms: float):
    """Record AgentCore service latency."""
    agentcore_latency_ms.observe(latency_ms)


def record_error(error_type: str):
    """Record a call error by type."""
    call_errors_total.labels(error_type=error_type).inc()


def record_pipeline_error():
    """Record a pipeline processing error."""
    pipeline_errors_total.inc()


def record_frame_processed(direction: str):
    """Record a processed frame (input or output)."""
    frames_processed.labels(direction=direction).inc()
