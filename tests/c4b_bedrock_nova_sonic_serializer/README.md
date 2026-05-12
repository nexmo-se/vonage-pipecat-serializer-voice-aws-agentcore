# C4b — Live Vonage + AWS Bedrock Nova Sonic Agent

**Full integration test:** Live voice-to-speech conversation via Vonage Voice API, Pipecat WebSocket audio serializer, and AWS Bedrock Nova Sonic.

## System Architecture

```
Caller Phone
    ↓
Vonage Voice API (receives call)
    ↓
GET /answer endpoint (returns NCCO with wss:// WebSocket URL)
    ↓
Vonage connects call to wss://agent-host/ws
    ↓
FastAPIWebsocketTransport (receives audio frames from Vonage)
    ↓
AWSNovaSonicLLMService (speech-to-speech: processes caller audio, generates response)
    ↓
Audio frames streamed back to Vonage
    ↓
Caller hears agent response
```

## Prerequisites Checklist

- [ ] C4a passed (AWS credentials + Bedrock model validation)
- [ ] Python 3.14+ with shared venv at `tests/c2_voice_linux_sdk/venv`
- [ ] AWS Bedrock access: `amazon.nova-2-sonic-v1:0` in `us-east-1`
- [ ] AWS credentials configured: `.env` file in repo root with `AWS_PROFILE=vonage-dev` or `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY`
- [ ] ngrok installed and authenticated
- [ ] Vonage account with voice-enabled number and dashboard application configured

## Environment Setup

### 1. Prepare AWS Credentials

Ensure one of these is set:

**Option A: Use profile-based credentials (recommended)**

```bash
# Verify profile exists
aws configure list --profile vonage-dev

# If missing, create it
aws configure --profile vonage-dev
# Enter: Access Key ID, Secret Access Key, Region: us-east-1
```

**Option B: Use environment file**

```bash
# In repo root .env file
AWS_PROFILE=vonage-dev
AWS_REGION=us-east-1
```

### 2. Verify Bedrock Nova Sonic Access

```bash
cd tests/c4b_bedrock_nova_sonic_serializer
source ../c2_voice_linux_sdk/venv/bin/activate
python test_bedrock.py
```

Expected output: ✓ Pass (verify Bedrock credentials and model access)

### 3. Install Missing Runtime Dependencies

```bash
pip install aws-sdk-bedrock-runtime aioboto3
```

## Running the Tests

### Phase 1: Validation Tests (No Phone Call Needed)

Run these to verify dependencies and permissions without live Vonage calls:

```bash
# Terminal 1: In c4b_bedrock_nova_sonic_serializer/
python test_bedrock.py        # ✓ Check Bedrock credentials and model
python test_integration.py    # ✓ Check Pipecat imports and Vonage config
```

Expected output: All tests pass (3 stages in each)

---

### Phase 2: Start Live Agent

#### 2a. Free port 8001 (if needed)

```bash
# Check if port is in use
lsof -iTCP:8001 -sTCP:LISTEN -n -P

# Clear it
lsof -ti tcp:8001 | xargs kill -9 2>/dev/null || true
sleep 1
```

#### 2b. Start agent (Terminal 1)

```bash
cd tests/c4b_bedrock_nova_sonic_serializer
source ../c2_voice_linux_sdk/venv/bin/activate
WS_PORT=8001 AWS_PROFILE=vonage-dev python bedrock_echo_agent.py
```

**Expected startup (within 3 seconds):**

```
2026-05-12 13:19:59.245 | INFO | pipecat:<module>:14 - ᓚᘏᗢ Pipecat 0.0.104.post2.dev1 ...
✓ AWS credentials resolved (profile: vonage-dev, region: us-east-1)

Bedrock Nova Sonic + Vonage Audio Serializer Agent
  Model:     amazon.nova-2-sonic-v1:0
  Region:    us-east-1
  Listening: ws://0.0.0.0:8001/ws

To connect a live call:
  1. Run: ngrok http 8001
  2. Set Vonage app Answer URL to: https://<ngrok-host>/answer
  3. Call your Vonage number — Vonage will connect to this agent

Press Ctrl+C to stop.
```

If you see `ERROR: [Errno 48] error while attempting to bind`, port 8001 is still in use. Re-run the port-clear commands above.

---

### Phase 3: Expose Agent with ngrok (Terminal 2)

```bash
# With reserved domain (recommended for testing)
ngrok http --domain=kittphi.ngrok.app 8001

# Or without reservation (generates random URL each time)
ngrok http 8001
```

**Expected output (Terminal 2):**

```
Session Status                online
Account                       <your-account>
Version                       3.x.x
Region                        us
Web Interface                 http://127.0.0.1:4040
Forwarding                    https://kittphi.ngrok.app -> http://localhost:8001
```

Note the HTTPS forwarding URL (e.g., `https://kittphi.ngrok.app`).

---

### Phase 4: Configure Vonage Dashboard

**In Vonage Dashboard → Applications → [Your App] → Edit:**

| Setting        | Value                                                    |
| -------------- | -------------------------------------------------------- |
| **Answer URL** | `https://kittphi.ngrok.app/answer` (use your ngrok host) |
| **Event URL**  | `https://kittphi.ngrok.app/`                             |

**Important notes:**

- Do NOT manually specify `/ws` in the dashboard — the agent's `/answer` endpoint handles that
- Update URLs immediately when you restart ngrok (ngrok host changes)

---

### Phase 5: Pre-Call Verification

```bash
# Terminal 3: Verify answer endpoint is routing correctly
curl -s https://kittphi.ngrok.app/answer | python -m json.tool
```

**Expected JSON response:**

```json
[
  {
    "action": "connect",
    "endpoint": [
      {
        "type": "websocket",
        "uri": "wss://kittphi.ngrok.app/ws",
        "content-type": "audio/l16;rate=16000"
      }
    ]
  }
]
```

If you see `{"detail":"Not Found"}`:

- Agent process crashed or wasn't restarted
- ngrok tunnel is dead
- Check Terminal 1 and Terminal 2 are still running

---

### Phase 6: Place Live Call

1. **Call your Vonage number** from your phone
2. **Listen for agent greeting:** Nova Sonic generates a welcome message
3. **Speak:** Agent will process your speech and respond
4. **Observe logs (Terminal 1):**

```
Answer webhook called → routing call to wss://kittphi.ngrok.app/ws
✓ Vonage connected: 216.147.2.103:0
✓ Listening for audio (Nova Sonic ready)…
[Audio frames flowing...]
User started speaking (VAD detected)
[Nova Sonic processing...]
User stopped speaking
[Response audio sent back to caller]
```

5. **Hang up** when done

---

### Phase 7: Stop Agent

```bash
# Terminal 1: Press Ctrl+C to gracefully shutdown
^C
Stopped. C4b live agent test complete ✓
```

Clean up:

```bash
# Kill ngrok (Terminal 2)
^C

# Optional: Clear agent log if it got large
rm -f agent.log
```

## Troubleshooting

### Port/Network Issues

| Symptom                                          | Root Cause                                     | Solution                                                        |
| ------------------------------------------------ | ---------------------------------------------- | --------------------------------------------------------------- |
| `[Errno 48] address already in use` on port 8001 | Previous agent or process still bound          | Run: `lsof -ti tcp:8001 \| xargs kill -9 2>/dev/null \|\| true` |
| `{"detail":"Not Found"}` from `/answer` endpoint | Stale agent process or ngrok dead              | Kill agent (Ctrl+C), restart agent, restart ngrok               |
| ngrok says "address already in use"              | Port 8001 still bound                          | Kill process first, then start ngrok                            |
| Vonage connects but agent process crashes        | Unrelated to port — check stderr in Terminal 1 | See "Pipeline/LLM Issues" below                                 |

### Pipeline/LLM Issues

| Symptom                                                          | Root Cause                                              | Solution                                                                                                             |
| ---------------------------------------------------------------- | ------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------- |
| `ModuleNotFoundError: No module named 'aws_sdk_bedrock_runtime'` | Missing runtime dependency                              | Run: `pip install aws-sdk-bedrock-runtime aioboto3`                                                                  |
| Bedrock access denied or throttle errors                         | Invalid credentials or region mismatch                  | Verify: `aws sts get-caller-identity --profile vonage-dev` and confirm us-east-1 model access                        |
| Agent starts but no response to calls                            | Audio not reaching Nova Sonic or response not sent back | Check logs for "User started speaking" — if missing, VAD issue; if present but no response, Nova Sonic/Bedrock issue |
| Call connects briefly then disconnects                           | Agent crash mid-pipeline                                | Check Terminal 1 stderr for tracebacks; common: serializer frame size mismatch                                       |
| Agent responds but audio cuts off                                | Bedrock latency or Vonage timeout                       | Normal for first response (~2s latency); try simple prompts                                                          |

### Vonage/ngrok Issues

| Symptom                                        | Root Cause                                                | Solution                                                                                          |
| ---------------------------------------------- | --------------------------------------------------------- | ------------------------------------------------------------------------------------------------- |
| Call rings but never connects                  | Answer URL not updated in dashboard or ngrok domain wrong | Double-check dashboard has correct ngrok host; re-copy from Terminal 2                            |
| Call connects, hear silence                    | No audio frames reaching agent or agent not responding    | Verify ngrok `Forwarding` line shows correct URL; check agent logs for "Vonage connected" message |
| Call works once, fails on second call          | ngrok tunnel changed or needs restart                     | Restart ngrok (`^C` in Terminal 2, then `ngrok http ...` again) and update dashboard              |
| Dashboard shows "Endpoint Unreachable" warning | ngrok tunnel is down or `/answer` endpoint 404ing         | Ensure ngrok is running (Terminal 2) and agent is running (Terminal 1)                            |

### Call Quality Issues

| Symptom                                          | Root Cause                                                | Solution                                                                         |
| ------------------------------------------------ | --------------------------------------------------------- | -------------------------------------------------------------------------------- |
| Caller hears voice but very delayed              | Normal for first call; Bedrock cold start                 | Subsequent calls are faster (~500ms latency)                                     |
| Agent cuts off mid-response                      | Vonage timeout or audio frame buffer overflow             | Normal edge case; try shorter prompts                                            |
| Agent repeats caller audio instead of responding | Configuration issue (should not happen with current code) | Stop agent, verify `/answer` returns correct WebSocket URI pointing to this host |

### Debugging

**Enable full pipecat logging:**

```bash
VONAGE_ENABLE_PIPECAT_LOGGER=1 WS_PORT=8001 AWS_PROFILE=vonage-dev python bedrock_echo_agent.py 2>&1 | tee agent.log
```

**Save call logs for analysis:**

```bash
# After call ends, logs are in agent.log (if using tee above)
tail -200 agent.log | grep -E "User|Nova|audio|Error" > call_analysis.txt
```

**Verify system readiness before calling:**

```bash
# All of these should succeed
aws sts get-caller-identity --profile vonage-dev
curl -s https://kittphi.ngrok.app/answer | python -m json.tool
ps aux | grep bedrock_echo_agent.py
```

## Known Issues & Workarounds

### Pipecat Adapter Bug (Already Patched)

The installed pipecat library has a bug in `aws_nova_sonic_adapter.py` where `ConvertedMessages()` is called without required arguments when messages list is empty. This is already patched in the shared venv, but if you reinstall pipecat from scratch, apply:

```bash
# In pipecat/adapters/services/aws_nova_sonic_adapter.py line ~124
# Change: return self.ConvertedMessages()
# To:     return self.ConvertedMessages(messages=[])
```

### VAD (Voice Activity Detection) Notes

- Silero VAD is loaded on first call (adds ~1.5s startup latency)
- Subsequent calls are faster
- Confidence threshold: 0.7 (adjust in code if too sensitive/loose)

---

## Next Steps

After C4b passes:

- **C5 (Optional):** AWS AgentCore runtime wrapper validation (tests/c5_agentcore_runtime/)
- **app/:** Full production deployment with Docker containers and deployment scripts
- **Documentation:** Use this README as reference for other test developers
