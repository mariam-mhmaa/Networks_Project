import binascii
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pc_test"))
from protocol import (MAX_DECODED, MAX_ENCODED, SlipDecoder, crc16, decode_atr,
                      encode_atr, slip_encode)
from protocol_cases import cases


class ProtocolTests(unittest.TestCase):
    def test_crc_reference_and_independent_implementation(self):
        self.assertEqual(crc16(b"123456789"), 0x29B1)
        for data in (b"", bytes(range(256)), b"\xc0\xdb" * 512):
            self.assertEqual(crc16(data), binascii.crc_hqx(data, 0xFFFF))

    def test_shared_complete_example(self):
        vector = json.loads(Path(__file__).with_name("protocol_vector.json").read_text())
        raw = encode_atr(vector["test_id"], vector["seq"], bytes.fromhex(vector["payload_hex"]))
        self.assertEqual(raw, bytes.fromhex(vector["atr_hex"]))
        self.assertEqual(slip_encode(raw), bytes.fromhex(vector["slip_hex"]))

    def test_parser_matrix(self):
        decoder = SlipDecoder()
        for case in cases():
            with self.subTest(case=case["name"]):
                output = bytearray()
                # Feed byte by byte, including escapes, with state across cases.
                for byte in case["tx"]:
                    for raw in decoder.feed(bytes([byte])):
                        try:
                            test_id, seq, payload = decode_atr(raw)
                        except ValueError:
                            continue
                        if test_id:
                            output.extend(slip_encode(encode_atr(test_id, seq, bytes(b ^ 0xA5 for b in payload))))
                self.assertEqual(bytes(output), case["expected"])
                self.assertLessEqual(len(decoder.buffer), MAX_DECODED)

    def test_limits_and_validation(self):
        self.assertEqual(MAX_DECODED, 1034)
        self.assertEqual(MAX_ENCODED, 2070)
        self.assertEqual(len(slip_encode(b"\xc0" * MAX_DECODED)), MAX_ENCODED)
        for args in ((1, 0, b"a" * 1025), (-1, 0, b""), (1, 2**32, b"")):
            with self.assertRaises(ValueError):
                encode_atr(*args)
        for raw in (b"", b"short", b"a" * 1035, encode_atr(1, 0, b"a")[:-1]):
            with self.assertRaises(ValueError):
                decode_atr(raw)

    def test_malformed_escape_and_overflow_count_once(self):
        for wire in (b"\xc0\xdb\x00abc\xc0", b"\xc0\xdb\xc0",
                     b"\xc0" + b"a" * 2000 + b"\xc0"):
            decoder = SlipDecoder()
            self.assertEqual(decoder.feed(wire), [])
            self.assertEqual(decoder.rejected, 1)
            self.assertEqual(decoder.feed(b"\xc0\xc0"), [])
            raw = encode_atr(1, 0, b"ok")
            self.assertEqual(decoder.feed(slip_encode(raw)), [raw])


if __name__ == "__main__":
    unittest.main()
