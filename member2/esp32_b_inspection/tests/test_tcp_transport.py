"""Compile actual C transport with MSVC; exercise it over real loopback TCP.

No ESP32, firmware flash, hotspot change, or application job execution.
Set B_VCVARS64 if Visual Studio's developer-environment script is elsewhere.
"""
from pathlib import Path
import json
import os
import socket
import struct
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]


def frame(payload):
    return struct.pack(">I", len(payload)) + payload


def exact(sock, size):
    data = bytearray()
    while len(data) < size:
        part = sock.recv(size - len(data))
        if not part:
            raise EOFError("connection ended before the complete test response")
        data.extend(part)
    return bytes(data)


def read_frame(sock):
    size, = struct.unpack(">I", exact(sock, 4))
    if not 1 <= size <= 1024:
        raise AssertionError(f"invalid response length: {size}")
    return exact(sock, size)


class TransportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        script = Path(os.environ.get("B_VCVARS64", r"C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars64.bat"))
        if not script.is_file():
            raise RuntimeError("Native transport verification needs MSVC; set B_VCVARS64")
        cls.scratch = tempfile.TemporaryDirectory(prefix="mct431-b-tcp-")
        cls.addClassCleanup(cls.scratch.cleanup)
        cls.exe = Path(cls.scratch.name) / "b_tcp_test.exe"
        args = ["cl", "/nologo", "/TC", "/std:c11", "/W4", "/WX", "/D_CRT_SECURE_NO_WARNINGS",
                "/I" + str(ROOT / "main"), str(ROOT / "main/tcp_frames.c"),
                str(ROOT / "main/tcp_service.c"), str(ROOT / "tests/tcp_host.c"),
                "/Fe" + str(cls.exe), "/link", "ws2_32.lib"]
        command = f'@echo off\ncall "{script}" >nul\nif errorlevel 1 exit /b 1\n' + subprocess.list2cmdline(args) + '\nexit /b %errorlevel%\n'
        (Path(cls.scratch.name) / "compile.cmd").write_text(command, encoding="utf-8")
        build = subprocess.run(["cmd.exe", "/d", "/c", "compile.cmd"], cwd=cls.scratch.name,
                               capture_output=True, text=True, timeout=60)
        if build.returncode:
            raise RuntimeError(build.stdout + build.stderr)

    def setUp(self):
        self.process = subprocess.Popen([str(self.exe)], stdout=subprocess.PIPE,
                                        stderr=subprocess.PIPE, text=True)
        self.addCleanup(self.stop_server)
        self.port = int(self.process.stdout.readline())

    def stop_server(self):
        if self.process.poll() is None:
            self.process.terminate()
        self.process.wait(timeout=5)
        self.process.stdout.close()
        self.process.stderr.close()

    def connect(self):
        sock = socket.create_connection(("127.0.0.1", self.port), timeout=2)
        self.addCleanup(sock.close)
        return sock

    def assert_closed(self, sock):
        try:
            self.assertEqual(sock.recv(1), b"")
        except ConnectionResetError:
            pass

    def test_actual_c_codec_and_tx_bounds(self):
        result = subprocess.run([str(self.exe), "--unit"], capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_pc_probe_against_actual_c_service(self):
        result = subprocess.run(
            [sys.executable, "-B", str(ROOT / "tools/probe_transport.py"),
             "127.0.0.1", "--port", str(self.port)],
            capture_output=True, text=True, timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["result"], "PASS")
        self.assertEqual(report["frames"], 2)

    def test_fragmented_utf8_message(self):
        sock = self.connect()
        payload = '{"label":"\u0641\u062d\u0635"}'.encode("utf-8")
        for byte in frame(payload):
            sock.sendall(bytes([byte]))
        self.assertEqual(read_frame(sock), payload)

    def test_back_to_back_messages(self):
        sock = self.connect()
        one, two = b'{"type":"ONE"}', b'{"type":"TWO"}'
        sock.sendall(frame(one) + frame(two))
        self.assertEqual(read_frame(sock), one)
        self.assertEqual(read_frame(sock), two)

    def test_maximum_frame(self):
        sock = self.connect()
        payload = b'"' + b'x' * 1022 + b'"'
        sock.sendall(frame(payload))
        self.assertEqual(read_frame(sock), payload)

    def test_zero_length_closes_connection(self):
        sock = self.connect()
        sock.sendall(struct.pack(">I", 0))
        self.assert_closed(sock)

    def test_oversized_length_closes_before_body(self):
        sock = self.connect()
        sock.sendall(struct.pack(">I", 1025))
        self.assert_closed(sock)

    def test_huge_length_closes_before_body(self):
        sock = self.connect()
        sock.sendall(struct.pack(">I", 0xFFFFFFFF))
        self.assert_closed(sock)

    def test_second_client_cannot_replace_silent_owner(self):
        first = self.connect()
        first.sendall(frame(b'"owner"'))
        self.assertEqual(read_frame(first), b'"owner"')
        second = self.connect()
        self.assert_closed(second)
        first.sendall(frame(b'"still-owner"'))
        self.assertEqual(read_frame(first), b'"still-owner"')

    def test_partial_frame_does_not_leak_to_new_connection(self):
        first = self.connect()
        first.sendall(b"\x00\x00\x00\x20partial")
        first.close()
        # Allow the polling server to observe EOF before admitting a new owner.
        time.sleep(0.05)
        second = self.connect()
        second.sendall(frame(b'"fresh"'))
        self.assertEqual(read_frame(second), b'"fresh"')

    def test_half_close_drains_already_queued_response(self):
        sock = self.connect()
        payload = b'"last-response"'
        sock.sendall(frame(payload))
        sock.shutdown(socket.SHUT_WR)
        self.assertEqual(read_frame(sock), payload)
        self.assert_closed(sock)


if __name__ == "__main__":
    unittest.main(verbosity=2)
