# Little Toy Works operator interface

Member 3's cartoon cat-and-puppy operator UI, prepared for a Milestone 1 gateway. The real gateway is not included. The browser no longer simulates production or decides PASS/FAIL. It sends HTTP commands and renders WebSocket snapshots.

Repository location: `member3/operator-ui/` on branch `member3/operator-ui`. Commands below run from this subsystem folder. See [repository setup](docs/repository_setup.md) and the [Member 4 handoff prompt](MEMBER4_PROMPT.md).

## Run the standalone test gateway

Python 3.10+ recommended. In PowerShell, from this folder:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-tested.txt
.\.venv\Scripts\python.exe mock_gateway.py --port 8080 --test-controls --log mock-gateway.log
```

Open **http://127.0.0.1:8080**. Keep Gateway address set to `http://127.0.0.1:8080`, click Connect if needed, wait for Gateway live, then Start. The same server hosts the screen, HTTP API and WebSocket. Its ESP stations are simulated. No Node/npm/build step is needed.

For another PC on the team network, use `--host 0.0.0.0` and open `http://GATEWAY_LAN_IP:8080` on the operator PC. Use the LAN IP in Gateway address, not the operator's localhost. Network/firewall setup is team-specific. Keep the test gateway on your team network; it has no authentication and is not a production service.

If the old static preview is still running on port 8765, it now contains the gateway client too. Put `http://127.0.0.1:8080` in its address field and run the test server with `--allow-origin http://127.0.0.1:8765`. Prefer the same-origin 8080 URL to avoid cross-origin configuration.

## Connect Member 4's gateway

Give Member 4 this whole folder and **GATEWAY_HANDOFF.md**. Implement its v1 endpoint/message contract, or agree on changes before integration. Host the UI assets alongside the real API, open the real gateway URL, set Gateway address to its origin, and Connect. There is no hidden fallback to simulated results. The address is remembered in this browser.

Device indicators describe what the gateway reports. A live UI connection does not imply both ESPs are online. Timers are visual estimates from gateway remaining times; only gateway results finish a job. A command notebook below the workshop separates delivery, acceptance and completion and exports JSON for debugging. Device-level proof still comes from gateway/device logs and captures.

## Test commands

```powershell
.\.venv\Scripts\python.exe -m unittest -v test_gateway.py
```

Optional Node 18+ (no npm dependencies):

```powershell
node test_client.mjs
```

These test the mock's real HTTP/WS exchange, deduplication, queue capacity, controls, rejection, restart, CORS and the client's protocol/reconnection/retry behavior. They do not verify real ESPs or replace browser visual inspection.

With `--test-controls` enabled, use a separate PowerShell terminal for controlled scenarios:

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8080/test/scenario -ContentType application/json -Body '{"action":"disconnect_b"}'
```

| Action | Expected screen behavior |
| --- | --- |
| `reject_next` | Next valid command gets a rejection; no action executes |
| `disconnect_a`, `disconnect_b` | Station disconnected, Fault reason, active motion stops; Stop can abort an active batch |
| `restore_devices` | Both devices connected; active Fault stays latched until Stop |
| `silence` | WS updates stop; UI becomes stale after 3.5s and reconnects; fresh GET may temporarily synchronize again |
| `resume_updates` | WS updates resume, followed by a fresh synchronized live display |
| `restart` | New gateway boot ID, no batch; old pending work is not resent |

For a full outage, stop/restart the server instead of `silence`. Reconnection should restore a complete snapshot before enabling controls. For Pause, accepted jobs may finish, then no new jobs start. For Stop, final partial results remain. For a completed default 12-part batch (`N=4`, `K=0`), expect 9 passed and 3 failed.

## Files for handoff

| File | Purpose |
| --- | --- |
| `index.html`, `cartoon.css`, `toys.css`, `integration.css` | Screen, approved theme and connection controls |
| `toys.js`, `motion.js`, `motion.css` | Cat/puppy drawings and gateway-driven effects |
| `app.js` | Forms, pending commands, truthful rendering, event notebook |
| `protocol.js` | Runtime validation for proposed v1 messages |
| `transport.js` | HTTP deadlines/retries, WebSocket buffering/reconnect/stale watchdog |
| `mock_gateway.py`, `requirements.txt` | Standalone test gateway and Python dependency |
| `requirements-tested.txt`, `TEST_RESULTS.md`, `examples/` | Verified dependency versions, verification scope and machine-readable message examples |
| `test_gateway.py`, `test_client.mjs` | Repeatable server and client checks |
| `GATEWAY_HANDOFF.md` | Exact API examples, fields, semantics and integration checklist |

Before submission, add your name/version/date, exact real gateway launch/address, real test outcomes, screenshots, packet captures and any remaining faults. The documented limits and API paths are proposed team choices; Member 4 must confirm compatibility. Milestone 2 MQTT, authentication and benchmarking controls are not implemented here.
