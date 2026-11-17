# ESP32 B SDK and physical communication checkpoint

This checkpoint now includes the implemented B application and gateway B subsystem. For normal configuration/inspection/recovery testing, use [the teammate handoff](member2-test-handoff.md) with diagnostic echo disabled. Member 1 and operator/full-system integration remain separate.

Verified on 2026-11-18: SDK activation/dependencies pass; 50 B-scoped software checks pass; normal application and diagnostic firmware compile/link successfully. Normal application has 23% application-partition headroom; diagnostic echo has 25%. Physical ESP32 communication is NOT RUN here. No board was flashed and no hotspot setting was changed.

## Local Windows setup

- SDK source: C:\Espressif\esp-idf-v6.1.1, official v6.1.1 tag.
- Tool/Python environment root: C:\Espressif.
- Session activation: dot-source C:\Espressif\activate-networks.ps1.
- Source of truth: this repository's member2/esp32_b_inspection on main.
- Short build staging folder: C:\Espressif\projects\inspection-b.

The EIM executable was downloaded from Espressif's official release and its
SHA256 was verified. EIM's source download/resume stalled; native Git and the
SDK's official idf_tools.py were used to finish the installation. Optional full
Clang compiler/library packages and other chip toolchains were excluded.
The session launcher does not change the machine-wide PATH or script policy.

Sixteen source/CMake/Kconfig/vendor files were copied to the short staging folder and
verified against the repository with SHA256. The local source-manifest.json
records them. No sdkconfig or credentials were copied. Before any subsequent
source change is tested/flashed, synchronize and verify the staging files again.

## Build commands in the short staging folder

```powershell
. C:\Espressif\activate-networks.ps1
Set-Location C:\Espressif\projects\inspection-b
python C:\Espressif\esp-idf-v6.1.1\tools\idf.py -B build-normal -D SDKCONFIG=sdkconfig.normal -D IDF_TARGET=esp32 build
python C:\Espressif\esp-idf-v6.1.1\tools\idf.py -B build-diagnostic -D SDKCONFIG=sdkconfig.diagnostic -D SDKCONFIG_DEFAULTS=sdkconfig.diagnostic.defaults -D IDF_TARGET=esp32 build
```

The local diagnostic defaults file selects
CONFIG_INSPECTION_TRANSPORT_DIAGNOSTIC=y. Normal firmware leaves it disabled.
The verified builds use the explicit non-secret placeholders MCT431_BUILD_ONLY
and build-only-placeholder, so the compiler links the networking path rather
than removing it after the blank-configuration guard. They are not real network
credentials. Configure the actual hotspot locally and rebuild before flashing.

## Optional physical echo diagnostic

For functional job/configuration tests, use the normal image and member2-test-handoff.md instead. The steps below are only the earlier echo diagnostic.

1. Connect only ESP32 B with a data-capable USB cable. Verify its USB identity,
   COM port, and chip before flashing. Do not assume the old COM3 assignment.
2. Enable the approved gateway PC hotspot using 2.4 GHz and WPA2, and verify
   the hardware supports it. The agreed router fallback needs a shared LAN.
3. Run the following from the staging folder and enter Wi-Fi credentials locally:

```powershell
python C:\Espressif\esp-idf-v6.1.1\tools\idf.py -B build-diagnostic -D SDKCONFIG=sdkconfig.diagnostic menuconfig
```

4. Rebuild that same configuration, then flash/monitor using B's verified port:

```powershell
python C:\Espressif\esp-idf-v6.1.1\tools\idf.py -B build-diagnostic -D SDKCONFIG=sdkconfig.diagnostic -p COMx flash monitor
```

5. Confirm the diagnostic-mode warning and B's current IPv4 address. Run
   member2/esp32_b_inspection/tools/probe_transport.py on the PC with that address.
   Its README contains the probe command. A PASS means two framed diagnostic
   payloads returned unchanged, including UTF-8 bytes.
6. Disable diagnostic echo before production application testing. No diagnostic
   response is a delivery/acceptance/completion acknowledgement or a verdict.

Keep credentials, sdkconfig, binaries, and raw configuration-bearing build
artifacts local. Share only credential-free test summaries.

Official references: [Windows SDK setup](https://docs.espressif.com/projects/esp-idf/en/stable/esp32/get-started/windows-setup.html)
and [EIM CLI commands](https://docs.espressif.com/projects/idf-im-ui/en/latest/cli_commands.html).
