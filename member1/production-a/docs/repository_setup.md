# Repository setup and contribution verification

This subsystem lives at `member1/production-a/` on branch
`member1/production-a` of mariam-mhmaa/Networks_Project. `main` contains only
the authorized shared-repository initialization README; the subsystem is not
merged into it. The original working project remains separate and untouched.

## Checkout and dependencies

```powershell
git clone --branch member1/production-a https://github.com/mariam-mhmaa/Networks_Project.git
Set-Location .\Networks_Project\member1\production-a
```

Use an existing ESP-IDF v6.1 installation, Python 3.11 (verified 3.11.9),
pyserial 3.5, CMake/Ninja/ESP toolchain supplied by ESP-IDF, and an existing
host GCC on PATH for the portable C history test. Do not substitute ESP's
cross compiler for host GCC. No installed toolchains or environments are
committed. This project does not require an upgrade/reinstall.

Activate an existing ESP-IDF terminal, or supply YOUR existing installation:

```powershell
$idfCheckout = Read-Host 'Existing ESP-IDF v6.1 directory containing export.ps1'
$toolsDirectory = Read-Host 'Existing ESP-IDF tools directory (blank for default/current)'
. .\docs\activate_idf.ps1 -IdfPath $idfCheckout -IdfToolsPath $toolsDirectory
idf.py --version
python --version
gcc --version
python -c "import serial; print(serial.__version__)"
```

When IDF_PATH is already set, `. .\docs\activate_idf.ps1` also works.
The helper changes only the current process environment and never installs
anything. If pyserial is missing, install `pc_test/requirements.txt` into your
chosen environment (`python -m pip install -r pc_test/requirements.txt`);
do not upgrade a working environment unnecessarily.

## Software-only verification

From THIS subsystem root:

```powershell
python -m unittest discover -s tests -v
```

Expected current result: 48 tests, including real portable C history execution
using host GCC. No COM port is accessed. The C test now uses an automatically
removed temporary directory; it no longer rewrites results/step5a_c_history.log
or leaves history_host_test.exe behind. New contribution verification goes in
verification/, separately from immutable original results/. Generated build
outputs/caches are ignored. All firmware files/settings and operational Python
client files are byte-identical to the verified working project.

## Firmware and hardware commands

See [acceptance.md](acceptance.md) for application-only build/flash commands
and recorded partition/flash settings. See [run.md](run.md) for hardware tests
and [continuation.md](continuation.md) for gateway API examples. Commands are
relative to this subsystem root, not the shared repository root. COM3 was the
verified board's port; always verify identity/port before any future flashing.
No build, flash, serial or hardware test was performed for this contribution.
Historical hardware tests deliberately reset RAM and overwrite their chosen
--log paths: choose NEW output paths under verification/generated/ to avoid
rewriting archived evidence. Do not run old raw Step 2 code against current
framed firmware. One serial reader owns the connection.

## Included, excluded and unchanged evidence

Included: firmware/main, CMakeLists.txt, sdkconfig and sdkconfig.defaults,
all Python client/diagnostic modules, requirements, tests, documentation and
raw results (JSON/CSV/log/partition captures), including failed attempts and
physical timing/fixture limitations. Historical paths and provenance remain
in raw evidence and progress notes. `.gitattributes` marks results/** as
non-text so Git preserves its original bytes/line endings.

Excluded: firmware/build, Python caches, host-test executables, environments,
installed toolchains, generated sdkconfig.old and unnecessary archives. Original
project brief PDF and team guide DOCX stay local, as agreed. No blanket results,
log, binary or sdkconfig ignore rule is applied. The firmware settings and
application behavior are unchanged. Only the activation helper, test artifact
location, ignores and current documentation were adapted for the repository.

The archived static API review is historical, not the current contract. The
current [gateway handoff](gateway_handoff.md) and [acceptance summary](acceptance.md)
distinguish completed Member 1 functionality from pending integration.
Station and client histories remain RAM-only; serial reading has one owner.
There is no persistence, batch manager, inspection sender, operator UI or
automatic restart/resumption. An uncertain part remains uncertain without
validated matching completion evidence; physical same-session recovery under
external power is still NOT RUN. Original discovery/fixture failures and
operator-confirmed physical timing are preserved honestly.
