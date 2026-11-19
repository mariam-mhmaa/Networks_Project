"""Repeatable local operator verification; never uses physical COM/ESP32 devices."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "verification/operator"


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    node = shutil.which("node") or str(Path.home()/".cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe")
    results = {}
    commands = {
        "backend": [sys.executable, "-B", "-m", "unittest", "discover", "-s", "gateway/operator/tests", "-p", "test_*.py"],
        "integration": [sys.executable, "-B", "-m", "unittest", "discover", "-s", "stations/production/tests", "-p", "test_integrated.py"],
        "inspection": [sys.executable, "-B", "-m", "unittest", "discover", "-s", "stations/inspection/tests", "-p", "test_*.py"],
        "frontend": [node, "--test", "operator_ui/test_client.mjs"],
    }
    for name, command in commands.items():
        run = subprocess.run(command, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=240)
        (OUT/f"{name}.log").write_bytes(run.stdout)
        output = run.stdout.decode("utf-8", errors="replace")
        count = re.search(r"Passed (\d+) client/protocol checks" if name == "frontend" else r"Ran (\d+) tests", output)
        results[name] = {"exit_code": run.returncode, "checks": int(count[1]) if count else None}
        print(f"{name}: {'PASS' if run.returncode == 0 else 'FAIL'}", flush=True)
    sources = []
    for directory in ("gateway/operator", "gateway/production", "gateway/inspection", "operator_ui"):
        for path in sorted((ROOT/directory).rglob("*")):
            if path.is_file() and path.suffix in {".py", ".js", ".mjs", ".css", ".html", ".txt"}:
                sources.append({"path": path.relative_to(ROOT).as_posix(), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    summary = {"timestamp_utc": datetime.now(timezone.utc).isoformat(), "results": results,
        "prior_station_regression": {"checks": 75, "commit": "7a6d088", "rerun_this_update": False},
        "browser_visual_qa": "Not run in this verification script",
        "physical_hardware": "Not used; native C peers and loopback HTTP/WebSocket only",
        "firmware_source_changed": False, "sources": sources}
    (OUT/"summary.json").write_text(json.dumps(summary, indent=2)+"\n", encoding="utf-8")
    return int(any(r["exit_code"] for r in results.values()))


if __name__ == "__main__":
    raise SystemExit(main())
