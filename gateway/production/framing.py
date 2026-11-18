"""Reusable ATR/CRC and bounded incremental SLIP; no application behavior."""
import struct

MAX_PAYLOAD = 1024
MAX_DECODED = 8 + MAX_PAYLOAD + 2
MAX_ENCODED = 2 * MAX_DECODED + 2
END, ESC, ESC_END, ESC_ESC = 0xC0, 0xDB, 0xDC, 0xDD


def crc16(data):
    crc = 0xFFFF
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ (0x1021 if crc & 0x8000 else 0)) & 0xFFFF
    return crc


def encode_atr(test_id, seq, payload):
    if not 0 <= test_id <= 0xFFFF or not 0 <= seq <= 0xFFFFFFFF:
        raise ValueError("ID/sequence out of range")
    if len(payload) > MAX_PAYLOAD:
        raise ValueError("payload too large")
    body = struct.pack(">HIH", test_id, seq, len(payload)) + bytes(payload)
    return body + struct.pack(">H", crc16(body))


def decode_atr(data):
    if not 10 <= len(data) <= MAX_DECODED:
        raise ValueError("invalid record size")
    test_id, seq, length = struct.unpack(">HIH", data[:8])
    if length > MAX_PAYLOAD or len(data) != length + 10:
        raise ValueError("declared length mismatch")
    if crc16(data[:-2]) != int.from_bytes(data[-2:], "big"):
        raise ValueError("CRC mismatch")
    return test_id, seq, bytes(data[8:-2])


def slip_encode(data):
    if len(data) > MAX_DECODED:
        raise ValueError("decoded frame too large")
    return bytes([END]) + bytes(data).replace(b"\xdb", b"\xdb\xdd").replace(
        b"\xc0", b"\xdb\xdc") + bytes([END])


class SlipDecoder:
    def __init__(self):
        self.buffer = bytearray()
        self.started = False
        self.escaped = False
        self.dropping = False
        self.rejected = 0

    def feed(self, data):
        frames = []
        for byte in data:
            if byte == END:
                if self.started and not self.dropping:
                    if self.escaped:
                        self.rejected += 1
                    elif self.buffer:
                        frames.append(bytes(self.buffer))
                self.started = True
                self.buffer.clear()
                self.escaped = self.dropping = False
                continue
            if not self.started or self.dropping:
                continue
            if self.escaped:
                self.escaped = False
                if byte not in (ESC_END, ESC_ESC):
                    self.rejected += 1
                    self.dropping = True
                    self.buffer.clear()
                    continue
                byte = END if byte == ESC_END else ESC
            elif byte == ESC:
                self.escaped = True
                continue
            if len(self.buffer) == MAX_DECODED:
                self.rejected += 1
                self.dropping = True
                self.buffer.clear()
            else:
                self.buffer.append(byte)
        return frames
