#!/usr/bin/env python3
"""c7: Validate answer/answer.py produces valid NCCO with AgentCore presigned WSS URL.

Invokes the handler directly (no Lambda deployment required) with the real
runtime ARN so the presigned URL API call is live.

Pass criteria:
  - handler returns HTTP 200
  - body is valid JSON
  - NCCO is a list with one action: { "action": "connect", "endpoint": [...] }
  - endpoint[0]["type"] == "websocket"
  - endpoint[0]["uri"] starts with "wss://"  (real presigned AgentCore URL)
  - endpoint[0]["content-type"] == "audio/l16;rate=16000"
  - 405 returned for non-GET requests
"""

from __future__ import annotations

import json
import os
import sys

RUNTIME_ARN = "arn:aws:bedrock-agentcore:us-east-1:589536902306:runtime/vonage_runtime_agent-GC5gEQBPPz"
VONAGE_NUMBER = "14155551234"
AWS_REGION = "us-east-1"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_event(method: str = "GET") -> dict:
    return {"requestContext": {"http": {"method": method}}}


def _invoke(method: str = "GET") -> dict:
    """Set env vars and call the handler."""
    os.environ["AGENTCORE_RUNTIME_ARN"] = RUNTIME_ARN
    os.environ["VONAGE_NUMBER"] = VONAGE_NUMBER
    os.environ["AWS_REGION"] = AWS_REGION
    os.environ["AWS_DEFAULT_REGION"] = AWS_REGION

    # Import lazily so env vars are set first
    answer_dir = os.path.join(
        os.path.dirname(__file__), "..", "..", "answer"
    )
    sys.path.insert(0, os.path.abspath(answer_dir))
    import answer  # noqa: PLC0415
    import importlib
    importlib.reload(answer)

    return answer.handler(_make_event(method), None)


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------

def check_405_on_non_get() -> str:
    resp = _invoke("POST")
    assert resp["statusCode"] == 405, f"Expected 405, got {resp['statusCode']}"
    return "PASS"


def check_200_with_ncco() -> tuple[str, dict]:
    resp = _invoke("GET")
    assert resp["statusCode"] == 200, f"Expected 200, got {resp['statusCode']}: {resp.get('body')}"

    body = json.loads(resp["body"])
    assert isinstance(body, list) and len(body) == 1, f"NCCO must be a 1-element list, got: {body}"

    action = body[0]
    assert action["action"] == "connect", f"action must be 'connect', got {action['action']}"
    assert "endpoint" in action and len(action["endpoint"]) == 1

    ep = action["endpoint"][0]
    assert ep["type"] == "websocket", f"endpoint type must be 'websocket', got {ep['type']}"
    assert ep["uri"].startswith("wss://"), f"URI must start with wss://, got {ep['uri']}"
    assert ep["content-type"] == "audio/l16;rate=16000", f"Wrong content-type: {ep['content-type']}"

    return "PASS", body


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    results: dict = {"stage": "c7_lambda_answer_presigned_ncco", "checks": {}}
    passed = 0
    failed = 0

    # Check 1: non-GET returns 405
    try:
        status = check_405_on_non_get()
        results["checks"]["non_get_returns_405"] = {"status": status}
        passed += 1
    except Exception as exc:
        results["checks"]["non_get_returns_405"] = {"status": "FAIL", "error": str(exc)}
        failed += 1

    # Check 2: GET returns 200 + valid NCCO + presigned WSS URI
    try:
        status, ncco = check_200_with_ncco()
        wss_uri = ncco[0]["endpoint"][0]["uri"]
        results["checks"]["get_returns_valid_ncco"] = {
            "status": status,
            "wss_uri_prefix": wss_uri[:80] + "...",
        }
        passed += 1
    except Exception as exc:
        results["checks"]["get_returns_valid_ncco"] = {"status": "FAIL", "error": str(exc)}
        failed += 1

    results["summary"] = {"passed": passed, "failed": failed}
    results["status"] = "PASS" if failed == 0 else "FAIL"

    print(json.dumps(results, indent=2))
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
