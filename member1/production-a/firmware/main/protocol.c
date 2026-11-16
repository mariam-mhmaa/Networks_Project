#include "protocol.h"
#include <string.h>

enum { END = 0xC0, ESC = 0xDB, ESC_END = 0xDC, ESC_ESC = 0xDD };

uint16_t atr_crc16(const uint8_t *data, size_t length)
{
    uint16_t crc = 0xFFFF;
    for (size_t i = 0; i < length; ++i) {
        crc ^= (uint16_t)data[i] << 8;
        for (int bit = 0; bit < 8; ++bit) {
            crc = (uint16_t)((crc << 1) ^ ((crc & 0x8000) ? 0x1021 : 0));
        }
    }
    return crc;
}

bool atr_validate(const uint8_t *data, size_t length)
{
    if (length < 10 || length > ATR_MAX_DECODED) return false;
    size_t payload = ((size_t)data[6] << 8) | data[7];
    if (payload > ATR_MAX_PAYLOAD || length != payload + 10) return false;
    uint16_t stored = ((uint16_t)data[length - 2] << 8) | data[length - 1];
    return stored == atr_crc16(data, length - 2);
}

int slip_feed(slip_decoder_t *s, uint8_t byte, size_t *length)
{
    if (byte == END) {
        int result = 0;
        if (s->started && !s->dropping) {
            if (s->escaped) result = -1;
            else if (s->length) { *length = s->length; result = 1; }
        }
        s->started = true;
        s->length = 0;
        s->escaped = s->dropping = false;
        return result;
    }
    if (!s->started || s->dropping) return 0;
    if (s->escaped) {
        s->escaped = false;
        if (byte != ESC_END && byte != ESC_ESC) {
            s->dropping = true;
            s->length = 0;
            return -1;
        }
        byte = byte == ESC_END ? END : ESC;
    } else if (byte == ESC) {
        s->escaped = true;
        return 0;
    }
    if (s->length == ATR_MAX_DECODED) {
        s->dropping = true;
        s->length = 0;
        return -1;
    }
    s->data[s->length++] = byte;
    return 0;
}

size_t slip_encode(const uint8_t *data, size_t length, uint8_t *output, size_t capacity)
{
    if (length > ATR_MAX_DECODED || capacity < 2) return 0;
    size_t used = 0;
    output[used++] = END;
    for (size_t i = 0; i < length; ++i) {
        size_t needed = (data[i] == END || data[i] == ESC) ? 2 : 1;
        if (used + needed + 1 > capacity) return 0;
        if (needed == 2) {
            output[used++] = ESC;
            output[used++] = data[i] == END ? ESC_END : ESC_ESC;
        } else output[used++] = data[i];
    }
    output[used++] = END;
    return used;
}

bool protocol_self_test(void)
{
    /* Same complete example as tests/protocol_vector.json, independently
     * computed with Python's standard-library binascii.crc_hqx. */
    static const uint8_t raw[] = {0x12,0x34,1,2,3,4,0,4,0,0xC0,0xDB,0xFF,0xC3,0x0E};
    static const uint8_t wire[] = {0xC0,0x12,0x34,1,2,3,4,0,4,0,0xDB,0xDC,0xDB,0xDD,0xFF,0xC3,0x0E,0xC0};
    uint8_t output[sizeof(wire)];
    if (atr_crc16((const uint8_t *)"123456789", 9) != 0x29B1 || !atr_validate(raw, sizeof(raw))) return false;
    if (slip_encode(raw, sizeof(raw), output, sizeof(output)) != sizeof(wire) ||
        memcmp(output, wire, sizeof(wire))) return false;
    slip_decoder_t state = {0};
    size_t length = 0;
    int frames = 0;
    for (size_t i = 0; i < sizeof(wire); ++i) {
        int result = slip_feed(&state, wire[i], &length);
        if (result < 0) return false;
        if (result == 1) {
            ++frames;
            if (length != sizeof(raw) || memcmp(state.data, raw, sizeof(raw))) return false;
        }
    }
    return frames == 1;
}
