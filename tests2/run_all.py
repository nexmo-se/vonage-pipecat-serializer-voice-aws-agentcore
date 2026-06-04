#!/usr/bin/env python3
"""Run tests2 stages in order with fail-fast behavior."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

STAGES = [
    ("c6_agentcore_ws_serializer_smoke", "test_c6_agentcore_ws_serializer_smoke.py"),
    ("c7_lambda_answer_presigned_ncco", "test_c7_lambda_answer_presigned_ncco.py"),
    ("c8_runtime_end_to_end_single_call", "test_c8_runtime_end_to_end_single_call.py"),
    ("c8b_runtime_bargein_disconnect", "test_c8b_runtime_bargein_disconnect.py"),
    ("c9_runtime_session_correlation", "test_c9_runtime_session_correlation.py"),
    ("c10_runtime_expiry_and_retry", "test_c10_runtime_expiry_and_retry.py"),
    ("c11_runtime_concurrency", "test_c11_runtime_concurrency.py"),
    ("c13_security_and_compliance", "test_c13_security_and_compliance.py"),
    ("c14_quota_and_region_matrix", "test_c14_quota_and_region_matrix.py"),
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run tests2 stage scripts in gate order.")
    parser.add_argument(
        "--start-at",
        default=STAGES[0][0],
        help="Stage folder name to start from (default: first stage).",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List stages and exit.",
    )
    return parser.parse_args()


def list_stages() -> None:
    for idx, (stage, _) in enumerate(STAGES, start=1):
        print(f"{idx}. {stage}")


def run_stage(tests2_dir: Path, stage: str, script: str) -> int:
    script_path = tests2_dir / stage / script
    if not script_path.exists():
        print(f"[FAIL] Missing script: {script_path}")
        return 2

    print(f"\n[RUN ] {stage}")
    result = subprocess.run([sys.executable, str(script_path)], cwd=str(tests2_dir.parent), check=False)
    if result.returncode == 0:
        print(f"[PASS] {stage}")
    else:
        print(f"[FAIL] {stage} (exit code {result.returncode})")
    return result.returncode


def main() -> int:
    args = parse_args()
    tests2_dir = Path(__file__).resolve().parent

    if args.list:
        list_stages()
        return 0

    stage_names = [name for name, _ in STAGES]
    if args.start_at not in stage_names:
        print(f"Unknown stage: {args.start_at}")
        print("Use --list to see valid stage names.")
        return 2

    start_index = stage_names.index(args.start_at)
    for stage, script in STAGES[start_index:]:
        exit_code = run_stage(tests2_dir, stage, script)
        if exit_code != 0:
            print("\nStopped on first failure.")
            return exit_code

    print("\nAll selected stages completed successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
