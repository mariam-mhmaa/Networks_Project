"""Windows native C / Python station verification; never opens a hardware port."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "verification/station-integration"


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    suites = [
        ("inspection", "stations/inspection/tests", "test_*.py"),
        ("production", "stations/production/tests", "test_integrated.py"),
        ("serial-link", "stations/production/tests", "test_serial_link.py"),
    ]
    results = {}
    for name, directory, pattern in suites:
        result = subprocess.run([sys.executable, "-B", "-m", "unittest", "discover", "-s", directory, "-p", pattern],
                                cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=240)
        (OUT / f"{name}.log").write_bytes(result.stdout)
        results[name] = {"exit_code": result.returncode, "log": f"{name}.log"}
        print(f"{name}: {'PASS' if result.returncode == 0 else 'FAIL'}", flush=True)
    sources = []
    for directory in ("shared/station", "gateway", "stations/production/firmware/main",
                      "stations/inspection/main"):
        for path in sorted((ROOT / directory).rglob("*")):
            if path.is_file() and path.suffix in {".c", ".h", ".py", ".txt"}:
                sources.append({"path": path.relative_to(ROOT).as_posix(),
                                "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    summary = {"timestamp_utc": datetime.now(timezone.utc).isoformat(),
               "scope": "Native C/Python software only; physical USB/Wi-Fi and operator UI NOT TESTED",
               "results": results, "sources": sources}
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return int(any(item["exit_code"] for item in results.values()))


if __name__ == "__main__":
    raise SystemExit(main())
