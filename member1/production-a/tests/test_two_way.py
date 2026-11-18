"""Check the host's stream handling without needing the board."""
import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pc_test"))
from two_way_test import check_case, read_exact


class PartialPort:
    def __init__(self, response=b""):
        self.response = bytearray(response)

    def read(self, count):
        result = bytes(self.response[:min(count, 2)])
        del self.response[:len(result)]
        return result

    def write(self, data):
        return min(2, len(data))


class StreamTests(unittest.TestCase):
    def test_accumulates_partial_reads(self):
        sizes = []
        self.assertEqual(read_exact(PartialPort(b"abcdef"), 6, 0.1, sizes), b"abcdef")
        self.assertEqual(sizes, [2, 2, 2])

    def test_incomplete_read_expires(self):
        self.assertEqual(read_exact(PartialPort(b"ab"), 4, 0.01, []), b"ab")

    def test_partial_writes_and_exact_binary(self):
        payload = bytes([0, 0xC0, 0xDB, 0xFF])
        record = {}
        self.assertTrue(check_case(PartialPort(bytes(v ^ 0xA5 for v in payload)),
                                   "binary", payload, 0.1, record))
        self.assertEqual(record["tx_hex"], payload.hex(" "))

    def test_corruption_and_extra_bytes_fail(self):
        for response in (b"wrong", b"\xA5debug"):
            with self.subTest(response=response):
                self.assertFalse(check_case(PartialPort(response), "bad", b"\x00", 0.1, {}))


if __name__ == "__main__":
    unittest.main()
