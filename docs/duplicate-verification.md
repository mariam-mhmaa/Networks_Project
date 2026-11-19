# Focused duplicate protection checks

Run the software checks from the repository root with the existing test environment:

```powershell
.\.venv\Scripts\python.exe -B tools/verify_duplicates.py --output Test_Cases/Evidences/Final_Verification/T06_Duplicate_Protection
```

The eight checks compile and run the actual portable C station application code
through native localhost peers. They cover duplicate HTTP commands, retransmitted
A/B jobs while active, completed-result replay, changed-content identity conflicts,
and reuse of the same part with a fresh job ID. The A/B heartbeat execution counters
must remain one where asserted. This is software evidence, not physical ESP32 or
radio evidence. It requires the same MSVC setup as the existing integration tests.
The output folder contains a verbose test log and JSON summary with source hashes.
No firmware or live gateway behavior changes are needed to run these checks.

The separate live HTTP duplicate check uses a previously completed Start request
recovered exactly from its original packet capture. Before replay, verify that
the gateway identity is unchanged, its command lookup still identifies that same
completed Start and batch, and the gateway is Idle and healthy. Capture the HTTP
traffic before issuing any replay. Send the identical original request twice;
both responses must be the same cached HTTP 202 acknowledgement. Send the same
ID with changed contents; expect HTTP 409 ID_CONFLICT. Confirm the original
command, batch history, station work and final counts remain unchanged. A cached
202 does not mean a new Start was executed. Abort rather than substitute a fresh
identity or gateway identity if preflight fails.

This live check validates operator-command duplicate protection at the physical
gateway. It does not inject duplicate jobs onto USB or TCP to the physical ESPs.
Do not open competing direct station clients while the integrated gateway owns
their links. Label this scope separately from the native station-code checks.
