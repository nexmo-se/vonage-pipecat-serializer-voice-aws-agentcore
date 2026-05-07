#!/usr/bin/env python3
"""C1: bootstrap a Vonage voice call id for serializer-based flows."""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = REPO_ROOT / ".env"
PLACEHOLDERS = {"", "your-vonage-call-id", "<your-vonage-call-id>", "your-vonage-session-id"}

load_dotenv(ENV_FILE)


def _resolve_private_key(path_value: str) -> Path:
    key_path = Path(path_value).expanduser()
    return key_path if key_path.is_absolute() else REPO_ROOT / key_path


def _load_config() -> tuple[str, Path, str]:
    app_id = os.getenv("VONAGE_APPLICATION_ID", "").strip()
    key_path = os.getenv("VONAGE_PRIVATE_KEY", "private.key").strip()
    call_id = os.getenv("VONAGE_CALL_ID", os.getenv("VONAGE_SESSION_ID", "")).strip()

    if not app_id:
        print("ERROR: VONAGE_APPLICATION_ID is not set")
        sys.exit(1)

    private_key = _resolve_private_key(key_path)
    if not private_key.exists():
        print(f"ERROR: private key file not found: {private_key}")
        sys.exit(1)

    return app_id, private_key, call_id


def _persist_call_id(call_id: str) -> None:
    if not ENV_FILE.exists():
        return

    lines = ENV_FILE.read_text(encoding="utf-8").splitlines()
    updated = False
    for i, line in enumerate(lines):
        if line.strip().startswith("VONAGE_CALL_ID="):
            lines[i] = f"VONAGE_CALL_ID={call_id}"
            updated = True
            break
    if not updated:
        lines.append(f"VONAGE_CALL_ID={call_id}")

    ENV_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    try:
        from vonage import Auth, Vonage
        from vonage_video import SessionOptions, TokenOptions
    except ImportError as exc:
        print(f"ERROR: Missing dependency — {exc}")
        print("Run: pip install -r requirements.txt")
        sys.exit(1)

    app_id, private_key, call_id = _load_config()
    client = Vonage(Auth(application_id=app_id, private_key=str(private_key)))

    if call_id.lower() in PLACEHOLDERS:
        print("Creating a new Vonage session id for voice serializer tests …")
        session = client.video.create_session(SessionOptions(media_mode="routed"))
        call_id = session.session_id
        _persist_call_id(call_id)
        print(f"✓ Saved VONAGE_CALL_ID={call_id} to {ENV_FILE}")
    else:
        print(f"✓ Using existing VONAGE_CALL_ID={call_id}")

    token = client.video.generate_client_token(TokenOptions(session_id=call_id, role="publisher"))
    if isinstance(token, bytes):
        token = token.decode("utf-8")

    print("\nCall bootstrap output")
    print("=" * 48)
    print(f"Application ID: {app_id}")
    print(f"Call ID:        {call_id}")
    print(f"Token:          {token}")
    print("=" * 48)
    print("C1 PASSED ✓")


if __name__ == "__main__":
    main()
