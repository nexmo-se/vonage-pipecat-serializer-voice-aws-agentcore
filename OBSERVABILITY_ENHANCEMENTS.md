# Observability & Reliability Enhancements

## Summary

Implemented two critical enhancements to the Vonage Pipecat Voice AWS AgentCore application:

### 1. OpenTelemetry + Prometheus Metrics (Observability)

**Files Modified:**

- `app/observability.py` (new module)
- `app/requirements.txt`
- `app/pyproject.toml`
- `app/main.py`

**What's New:**

#### Prometheus Metrics Export

- **Call Metrics:**
  - `voice_calls_total` — Counter for total calls by status (connected, completed, failed)
  - `voice_call_duration_seconds` — Histogram of call durations (buckets: 1s, 5s, 10s, 30s, 60s, 120s, 300s, 600s)
  - `voice_call_errors_total` — Counter of errors by type
- **Bedrock/Nova Sonic Metrics:**
  - `bedrock_latency_ms` — Histogram of Bedrock service latency (buckets: 10ms, 50ms, 100ms, 200ms, 500ms, 1s, 2s, 5s)
  - `bedrock_errors_total` — Counter of Bedrock service errors

- **AgentCore Metrics:**
  - `agentcore_latency_ms` — Histogram of AgentCore invocation latency (buckets: 10ms, 50ms, 100ms, 200ms, 500ms, 1s, 2s)
  - `agentcore_validation_failures_total` — Counter of validation failures by reason

- **Pipeline Metrics:**
  - `voice_frames_processed_total` — Counter of frames processed (input/output)
  - `voice_pipeline_errors_total` — Counter of pipeline errors

#### OpenTelemetry Integration

- Tracer provider initialized for future distributed tracing
- Span context manager (`trace_span`) for adding observability to async operations
- Foundation for end-to-end tracing from Vonage → Pipecat → Bedrock

#### New `/metrics` Endpoint

- GET `/metrics` returns Prometheus-format metrics
- Ready for Prometheus scraping
- Compatible with monitoring stacks (Grafana, DataDog, etc.)

**Usage:**

```bash
# Scrape metrics (e.g., with Prometheus)
curl http://localhost:8000/metrics

# In prometheus.yml
scrape_configs:
  - job_name: 'voice-agent'
    static_configs:
      - targets: ['localhost:8000']
```

---

### 2. AgentCore Response Validation (Reliability)

**Files Modified:**

- `app/observability.py` (new module with validation function)
- `app/agent.py` (integrated validation)

**What's New:**

#### Response Validation Function

```python
def validate_agentcore_response(response: str) -> tuple[bool, str | None]:
    """
    Validates AWS Bedrock AgentCore response structure.

    Checks:
    - Response is not empty
    - Response is valid JSON
    - Response is a dictionary

    Returns: (is_valid, error_reason)
    """
```

#### Enhanced AgentCore Bootstrap

- **Before:** Assumed response was always valid
- **After:** Validates response structure and content
- **On Failure:** Logs warning, increments validation failure counter, continues without context
- **Metrics:** `agentcore_validation_failures_total` tracks failure reasons:
  - `empty_response`
  - `invalid_json`
  - `not_dict`

#### Error Handling Improvements

- **Timeout Protection:** Records AgentCore latency to identify slow responses
- **Fallback Behavior:** If validation fails, agent continues with fresh LLM context
- **Observability:** All validation failures are logged and metrics-tracked

**Example:**

```python
# Validation failure log:
# logger.warning("AgentCore response validation failed",
#               reason="invalid_json",
#               response_preview="truncated...")

# AgentCore continues with empty context instead of crashing
```

---

## Dependencies Added

```
opentelemetry-api>=1.24.0
opentelemetry-sdk>=1.24.0
opentelemetry-exporter-prometheus>=0.45b0
prometheus-client>=0.20.0
```

---

## Code Changes Detail

### agent.py

1. Added `import time` for latency tracking
2. Added imports from `observability` module:
   - `record_agentcore_latency()` — Track invocation time
   - `record_call_duration()` — Track total call duration
   - `record_error()` — Record error types
   - `validate_agentcore_response()` — Validate response
   - `trace_span()` — Span context manager (for future use)

3. Added `_call_start_time` attribute to `VonageSerializerVoiceAgent`
4. Modified `invoke_agentcore_bootstrap()`:
   - Record AgentCore latency with `time.time()`
   - Validate response before using it
   - Log validation failures
   - Increment validation failure metrics
5. Modified `handle_call()`:
   - Set `self._call_start_time = time.time()` at start
   - Track call status (completed/failed/cancelled)
   - Record `record_call_duration()` with status in finally block

### main.py

1. Added imports:
   - `from prometheus_client import generate_latest, REGISTRY`
   - `from observability import init_observability`
2. Added initialization: `init_observability()` on module load
3. Added `/metrics` endpoint:
   - GET endpoint returning Prometheus-format metrics
   - Response content-type: `text/plain; version=0.0.4`
4. Updated docstring to document `/metrics` endpoint

### observability.py (New Module)

- Complete observability implementation:
  - Prometheus metrics definitions
  - OpenTelemetry provider initialization
  - `trace_span()` context manager
  - `validate_agentcore_response()` validation function
  - Metric recording helper functions

---

## Monitoring Setup (Optional)

### Docker Compose + Prometheus Example

```yaml
version: "3.9"
services:
  app:
    build: ./app
    ports:
      - "8000:8000"

  prometheus:
    image: prom/prometheus:latest
    ports:
      - "9090:9090"
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml
    command:
      - "--config.file=/etc/prometheus/prometheus.yml"
```

### prometheus.yml

```yaml
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: "voice-agent"
    static_configs:
      - targets: ["app:8000"]
```

---

## Testing

### Verify Metrics Endpoint

```bash
# In one terminal:
docker compose --profile app up app

# In another terminal:
curl http://localhost:8000/metrics

# Output: Prometheus-format metrics
# HELP voice_calls_total Total number of voice calls
# TYPE voice_calls_total counter
# voice_calls_total{status="completed"} 0
# ...
```

### Verify AgentCore Response Validation

Watch logs during calls with:

```bash
docker compose --profile app logs -f app
```

You'll see:

- `"event": "agentcore_bootstrap_failed"` on validation errors
- Counters for `agentcore_validation_failures_total`
- Call duration metrics

---

## Backward Compatibility

✅ **Fully Backward Compatible**

- All changes are additive (no breaking changes)
- Observability is optional (graceful fallback if init fails)
- Validation doesn't break flow (fallback to empty context)
- Existing API endpoints unchanged

---

## Next Steps

### Immediate (Deploy This Week)

1. ✅ Code deployed and tested
2. ✅ Metrics endpoint available at `/metrics`
3. ✅ AgentCore response validation active

### Short-term (Next 2 Weeks)

1. Set up Prometheus to scrape metrics
2. Create Grafana dashboards for:
   - Call success rate (`voice_calls_total`)
   - Call duration distribution (`voice_call_duration_seconds`)
   - Bedrock latency (`bedrock_latency_ms`)
   - Error rates (`voice_call_errors_total`)

### Medium-term (Next Month)

1. Add OpenTelemetry distributed tracing
2. Export traces to Jaeger or Datadog
3. Set up alerting on:
   - Call failure rate > 5%
   - Bedrock latency > 500ms (p95)
   - AgentCore validation failures

---

## References

- [Prometheus Client Library (Python)](https://github.com/prometheus/client_python)
- [OpenTelemetry Python](https://opentelemetry.io/docs/languages/python/)
- [Prometheus Metrics Best Practices](https://prometheus.io/docs/practices/naming/)
- [AUDIT_REPORT.md](../AUDIT_REPORT.md) — Tier 3 enhancements
