"""Compile/run portable firmware history code without overwriting raw evidence."""
from pathlib import Path
import os
import shutil
import subprocess
import tempfile
import unittest


class HistoryCoreTests(unittest.TestCase):
    def test_actual_c_history(self):
        root = Path(__file__).resolve().parents[1]
        compiler = shutil.which("gcc")
        self.assertIsNotNone(compiler, "Existing host GCC required; do not substitute ESP cross compiler")
        with tempfile.TemporaryDirectory(prefix="mct431-history-") as scratch:
            exe = Path(scratch) / ("history_host_test.exe" if os.name == "nt" else "history_host_test")
            build = subprocess.run([compiler, "-std=c99", "-Wall", "-Wextra",
                                    "-I" + str(root / "firmware/main"),
                                    str(root / "firmware/main/history.c"),
                                    str(root / "tests/history_core_test.c"), "-o", str(exe)],
                                   capture_output=True, text=True, timeout=30)
            self.assertEqual(build.returncode, 0, build.stdout + build.stderr)
            run = subprocess.run([str(exe)], capture_output=True, text=True, timeout=5)
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
