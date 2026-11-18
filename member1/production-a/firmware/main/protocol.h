#pragma once
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define ATR_MAX_PAYLOAD 1024
#define ATR_MAX_DECODED (8 + ATR_MAX_PAYLOAD + 2)
#define SLIP_MAX_ENCODED (2 * ATR_MAX_DECODED + 2)

typedef struct {
    uint8_t data[ATR_MAX_DECODED];
    size_t length;
    bool started, escaped, dropping;
} slip_decoder_t;

uint16_t atr_crc16(const uint8_t *data, size_t length);
bool atr_validate(const uint8_t *data, size_t length);
/* -1: reject once; 0: incomplete/empty; 1: data holds a complete frame. */
int slip_feed(slip_decoder_t *state, uint8_t byte, size_t *length);
size_t slip_encode(const uint8_t *data, size_t length, uint8_t *output, size_t capacity);
bool protocol_self_test(void);
