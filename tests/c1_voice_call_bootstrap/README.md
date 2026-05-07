# C1 — Voice Call Bootstrap

## Prerequisites

- `.env` has `VONAGE_APPLICATION_ID` and `VONAGE_PRIVATE_KEY`
- `private.key` exists

## Run commands

```bash
cd tests/c1_voice_call_bootstrap
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python test_voice_bootstrap.py
```

## Expected output

- Prints `C1 PASSED ✓`
- Writes/updates `VONAGE_CALL_ID` in root `.env`

## Troubleshooting

- `Missing dependency`: run `pip install -r requirements.txt`
- `private key file not found`: fix `VONAGE_PRIVATE_KEY` path
- Auth failures: verify `VONAGE_APPLICATION_ID` and key pair
