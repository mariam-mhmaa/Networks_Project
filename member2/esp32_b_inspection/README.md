# ESP32 B Inspection Station

This project is the inspection station for MCT431 Milestone 1. The current
firmware retains Member 2's Wi-Fi setup and now includes the approved TCP
transport foundation on main. Inspection/configuration/query message
contracts remain to be agreed; no inspection work is currently accepted.

## Current TCP transport checkpoint

- B listens on a configurable TCP port (default 5001); the gateway connects.
- One active controlling connection; an extra peer is closed without replacing it.
- Four-byte unsigned big-endian length counts following payload bytes only.
- Payload length is 1-1024 bytes. The framing layer preserves bytes; the future
  application layer will validate UTF-8 JSON and semantic message fields.
- Partial prefixes/bodies and multiple frames per read are handled incrementally.
- Zero/oversized lengths close the peer before an oversized body is read.
- Receive/send sockets are nonblocking, each poll has a finite receive budget,
  and a bounded four-frame TX queue copies outgoing payloads. Queue failure is
  explicit; this transport queue is not the future persistent result cache.
- Disconnect clears only connection framing/TX state. Keep both TCP directions
  open for future asynchronous lifecycle traffic. A peer half-close drains
  already queued frames and closes; it is not an application cancellation.
- `receive_frame` normally logs frame lengths without sending application ACKs
  or executing jobs. An explicit test-only echo option is described below and
  is disabled by default.

Eleven host checks compile and exercise the actual C framing/service modules
with MSVC (C11, /W4 /WX) and real loopback TCP. They cover frame boundaries,
maximum/bad sizes, UTF-8 byte preservation, bounded queue ownership, second
client rejection, disconnect/reconnect isolation, half-close draining, and
the standalone PC diagnostic probe.

Run from this subsystem directory:

```powershell
python -B -m unittest discover -s tests -v
```

The test runner uses an existing MSVC installation; set `B_VCVARS64` to its
`vcvars64.bat` path if it differs from the default Visual Studio 2022 Community
location. Temporary native binaries are cleaned up. Tests do not access an
ESP32, change hotspot settings, flash firmware, or execute inspection jobs.
Evidence is in `verification/tcp_transport_tests.log` and
`verification/tcp_transport_summary.json`.

ESP-IDF v6.1.1 is installed. Normal and optional diagnostic firmware compile and
link with the Wi-Fi/TCP path included using explicit non-secret placeholder
network settings. Both fit the configured application partition with 25% free.
Build evidence is in verification/esp_idf_build_summary.json. Physical
board/network and inspection-application tests are NOT RUN. Follow the
[local SDK/test procedure](../../docs/esp-idf-testing.md) before flashing.

## Physical TCP diagnostic

1. Use the approved gateway PC hotspot at 2.4 GHz with WPA2. Check actual
   availability and peer reachability; a router is the agreed fallback.
2. Connect only the identified ESP32 B over a data-capable USB cable. Determine
   its current COM port; the historical COM3 value is not an instruction to
   flash whichever device happens to own COM3.
3. In an activated ESP-IDF terminal, run `idf.py menuconfig`. Under
   **Inspection Station Wi-Fi**, enter the hotspot name and password locally.
   Do not put the password in source code or a shared message.
4. Under **Inspection Station TCP**, enable **Enable test-only framed echo**.
   Build, then flash and monitor using B's verified port:
   `idf.py -p COMx flash monitor`. Exit the monitor with Ctrl+].
5. Look for the diagnostic-mode warning and B's current
   `Wi-Fi connected; IPv4 address: ...` in the serial log.
6. From the PC, run the following with that address:

```powershell
python -B tools/probe_transport.py B_CURRENT_IP --port 5001
```

The probe sends two length-prefixed JSON test payloads, including UTF-8 bytes,
and requires byte-for-byte matching framed replies within its timeout. A PASS
proves this diagnostic's PC-to-B round trip. It does not verify the future
gateway operation controller, configuration commands, inspection verdicts,
acknowledgements, or result recovery. The diagnostic has no such messages.
Disable the echo option before production application testing.

Windows source paths containing spaces can prevent ESP-IDF builds. If a short
build staging folder is needed, keep this repository as the source of truth,
copy only this project's source/CMake/Kconfig files, and verify their hashes.
Do not copy a credential-bearing sdkconfig into Git or shared evidence.

The local `sdkconfig` and `build/` files are ignored by Git because they can
contain the hotspot password. Firmware binaries also embed the configured
network credentials, so do not share them as public artifacts.

The Wi-Fi connection proves that the ESP32 obtained an address. It does not
prove physical PC-to-B TCP reachability; that remains a hardware check for
the newly added transport checkpoint.

## First hotspot test

On 2026-11-17, ESP32 B joined the iPhone hotspot using WPA2 and received
`172.20.10.3`. The PC was connected to the same SSID. This address is assigned
by the hotspot and may change, so check the serial log again before the TCP
test.
