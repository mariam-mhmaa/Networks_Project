# Member 3 repository setup

The operator subsystem is contributed to `mariam-mhmaa/Networks_Project` on
branch `member3/operator-ui`, under `member3/operator-ui/`, following the
separate-branch/subsystem-folder pattern of the other members. This branch is
based on `origin/main`. It does not merge the Member 1/2 implementations or
change their source, and does not change the shared root README.

## Independent checkout

```powershell
git clone --branch member3/operator-ui https://github.com/mariam-mhmaa/Networks_Project.git Networks_Project_Member3
Set-Location .\Networks_Project_Member3\member3\operator-ui
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-tested.txt
.\.venv\Scripts\python.exe mock_gateway.py --port 8080 --test-controls
```

Open `http://127.0.0.1:8080`. The browser labels this as a **test gateway**;
its stations and verdicts are simulated. No Node/npm/build step is needed
to run the screen. Python 3.10+ is needed only for the mock and Python tests.

## Repeatable checks

From this subsystem folder:

```powershell
.\.venv\Scripts\python.exe -m unittest -v test_gateway.py
node test_client.mjs
```

The optional JavaScript test runner requires Node 18+ and no npm packages.
The contribution verification records are under `verification/`. The original
pre-repository verification scope is in `TEST_RESULTS.md`. Neither claims
real gateway/ESP32 integration or browser visual acceptance.

## Real gateway integration

Read `GATEWAY_HANDOFF.md`. Serve the listed UI assets
with the real gateway's API, or explicitly configure cross-origin HTTP and
WebSocket access. Set the screen's Gateway address to the real gateway origin.
The real gateway must implement/agree on the versioned contract before the UI
can be live. IDs, cache lifetime, boot/session identity, applied settings,
acceptance/completion and full snapshots are functional requirements of this
adapter. There is no automatic mock fallback.

## Included and excluded

Included: approved UI/theme/artwork, HTTP/WS adapter, validation, test gateway,
test sources, exact JSON message examples, handoff documentation, tested
dependency versions and fresh contribution verification.

Excluded: local virtual environments/dependency installs, caches, compiled
Python, generated runtime logs, ZIP bundles, original course PDF/DOCX files,
editor settings, credentials and unrelated work. The original `operator-preview`
working directory stays separate from this repository contribution.

Member 4 should bring this contribution into an integration branch through
normal review/merge or cherry-pick, without force-pushing or treating mock
results as hardware evidence. Member 2's inspected remote README currently
describes a Wi-Fi-only firmware stage; inspect its latest contract before
assuming TCP jobs/results are implemented.
