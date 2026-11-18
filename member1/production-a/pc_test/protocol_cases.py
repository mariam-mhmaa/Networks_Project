"""Functional cases shared by software tests and hardware runner."""
import struct
from protocol import MAX_DECODED, encode_atr, crc16, slip_encode


def cases():
    result = []

    def valid(name, requests, split=0):
        tx = b"".join(slip_encode(encode_atr(t, s, p)) for t, s, p in requests)
        rx = b"".join(slip_encode(encode_atr(t, s, bytes(b ^ 0xA5 for b in p)))
                      for t, s, p in requests)
        result.append(dict(name=name, tx=tx, expected=rx, split=split))

    valid("shared_example", [(0x1234, 0x01020304, bytes.fromhex("00 c0 db ff"))])
    valid("text", [(1, 1, b"MCT431 ATR test\r\n")])
    valid("special_bytes", [(1, 2, bytes.fromhex("00 c0 db ff 41 00 ff"))])
    valid("all_256", [(1, 3, bytes(range(256)))])
    valid("empty_payload", [(1, 4, b"")])
    valid("maximum_payload", [(1, 5, bytes([0xC0, 0xDB]) * 512)])
    valid("one_byte_pieces", [(1, 6, bytes.fromhex("00 c0 db ff"))], split=1)
    valid("three_frames_together", [(1, 7, b"one"), (2, 0xFFFFFFFF, b"two\xc0"), (65535, 9, b"\xdbthree")])
    valid("empty_frames_ignored", [(1, 10, b"empty delimiters")])
    result[-1]["tx"] = b"\xc0\xc0" + result[-1]["tx"] + b"\xc0\xc0"

    raw = encode_atr(1, 20, b"bad")
    wrong_length = bytearray(raw[:-2])
    wrong_length[7] += 1
    wrong_length += struct.pack(">H", crc16(wrong_length))
    excessive_header = struct.pack(">HIH", 1, 20, 1025)
    excessive_header += struct.pack(">H", crc16(excessive_header))
    invalids = [
        ("incorrect_crc", slip_encode(raw[:-1] + bytes([raw[-1] ^ 1]))),
        ("declared_length", slip_encode(wrong_length)),
        ("invalid_escape", b"\xc0\x01\xdb\x00\x02\xc0"),
        ("dangling_escape", b"\xc0\x01\xdb\xc0"),
        ("truncated_header", slip_encode(raw[:7])),
        ("truncated_crc", slip_encode(raw[:-1])),
        ("oversized_frame", b"\xc0" + b"A" * (MAX_DECODED + 1) + b"\xc0"),
        ("over_limit_length", slip_encode(excessive_header)),
        ("reserved_test_id", slip_encode(encode_atr(0, 20, b"reserved"))),
        ("unterminated_record", b"\xc0" + raw[:5]),
    ]
    for index, (name, wire) in enumerate(invalids):
        result.append(dict(name=name + "_silent", tx=wire, expected=b"", split=0))
        request = encode_atr(1, 100 + index, b"recovery\xc0\xdb\x00\xff")
        response = encode_atr(1, 100 + index, bytes(b ^ 0xA5 for b in b"recovery\xc0\xdb\x00\xff"))
        # One write: invalid input immediately followed by valid frame.
        result.append(dict(name=name + "_immediate_recovery", tx=wire + slip_encode(request),
                           expected=slip_encode(response), split=0))
    return result
