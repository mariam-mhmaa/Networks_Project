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
- `receive_frame` currently logs frame lengths without sending invented ACKs
  or executing jobs. Echo behavior exists only in the native test harness.

Ten host checks compile and exercise the actual C framing/service modules
with MSVC (C11, /W4 /WX) and real loopback TCP. They cover frame boundaries,
maximum/bad sizes, UTF-8 byte preservation, bounded queue ownership, second
client rejection, disconnect/reconnect isolation, and half-close draining.

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

The ESP-IDF toolchain has not been located/configured in the current session.
An ESP-IDF firmware build and board/network tests are NOT RUN; native Windows
tests do not validate the ESP-IDF integration path or final inspection behavior.

## Configure the first Wi-Fi test

1. Turn on the iPhone Personal Hotspot. Enable **Maximize Compatibility** if
   available, so the hotspot uses 2.4 GHz and WPA2.
2. Connect the PC to that hotspot.
3. Open this folder in VS Code and run **ESP-IDF: SDK Configuration Editor**.
4. Under **Inspection Station Wi-Fi**, enter the hotspot name and password,
   then save. Do not put the password in source code or a shared message.
5. Build the project, flash the ESP32 through COM3 using UART, and open the
   serial monitor. Look for `Wi-Fi connected; IPv4 address: ...`.

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
