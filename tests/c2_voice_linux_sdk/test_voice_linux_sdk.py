#!/usr/bin/env python3
"""C2: validate Linux voice SDK connectivity for serializer flows."""

import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv


def find_repo_root(start: Path) -> Path:
    current = start.resolve()
    for candidate in (current, *current.parents):
        if (candidate / ".env").exists():
            return candidate
    workspace_root = Path("/workspace")
    if (workspace_root / ".env").exists():
        return workspace_root
    return start.resolve()


REPO_ROOT = find_repo_root(Path(__file__).parent)
load_dotenv(REPO_ROOT / ".env")


def main() -> None:
    app_id = os.getenv("VONAGE_APPLICATION_ID", "").strip()
    key_path = os.getenv("VONAGE_PRIVATE_KEY", "private.key").strip()
    call_id = os.getenv("VONAGE_CALL_ID", os.getenv("VONAGE_SESSION_ID", "")).strip()

    missing = []
    if not app_id:
        missing.append("VONAGE_APPLICATION_ID")
    if not call_id:
        missing.append("VONAGE_CALL_ID")
    if missing:
        print(f"ERROR: Missing env vars: {', '.join(missing)}")
        sys.exit(1)

    private_key = Path(key_path)
    if not private_key.is_absolute():
        private_key = REPO_ROOT / key_path
    if not private_key.exists():
        print(f"ERROR: Private key not found: {private_key}")
        sys.exit(1)

    try:
        from vonage import Auth, Vonage
        from vonage_video import TokenOptions
        from vonage_video_connector import VonageVideoClient
        from vonage_video_connector.models import LoggingSettings, SessionAudioSettings, SessionAVSettings, SessionSettings
    except ImportError as exc:
        print(f"ERROR: Missing dependency — {exc}")
        print("Run: pip install -r requirements.txt")
        sys.exit(1)

    client = Vonage(Auth(application_id=app_id, private_key=str(private_key)))
    token = client.video.generate_client_token(TokenOptions(session_id=call_id, role="publisher"))
    if isinstance(token, bytes):
        token = token.decode("utf-8")

    print(f"Connecting Linux SDK bridge to call {call_id} …")
    connector = VonageVideoClient()
    state = {"connected": False, "error": None}

    def on_connected(_session):
        state["connected"] = True

    def on_disconnected(_session):
        return None

    def on_error(_session, error_description, error_code):
        state["error"] = f"{error_description} (Code: {error_code})"

    success = connector.connect(
        application_id=app_id,
        session_id=call_id,
        token=token,
        session_settings=SessionSettings(
            enable_migration=False,
            av=SessionAVSettings(
                audio_subscribers_mix=SessionAudioSettings(sample_rate=48000, number_of_channels=1)
            ),
            logging=LoggingSettings(level="INFO"),
        ),
        on_connected_cb=on_connected,
        on_disconnected_cb=on_disconnected,
        on_error_cb=on_error,
    )

    if not success:
        print("ERROR: Linux SDK connect() returned False")
        sys.exit(1)

    deadline = time.time() + 10
    while not state["connected"] and not state["error"] and time.time() < deadline:
        time.sleep(0.05)

    if state["error"]:
        print(f"ERROR: {state['error']}")
        sys.exit(1)
    if not state["connected"]:
        print("ERROR: Timed out waiting for Linux SDK connection")
        sys.exit(1)

    print("✓ Linux SDK bridge connected")
    time.sleep(3)
    connector.disconnect()
    print("✓ Linux SDK bridge disconnected")
    print("C2 PASSED ✓")


if __name__ == "__main__":
    main()
