#pragma once
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define B_PAYLOAD_MAX 1024u
#define B_FRAME_MAX (B_PAYLOAD_MAX + 4u)

typedef struct {
    uint8_t prefix[4];
    unsigned prefix_used;
    uint32_t expected;
    size_t used;
    bool invalid;
    uint8_t payload[B_PAYLOAD_MAX];
} b_frame_reader;

/* Feed arbitrary TCP fragments one byte at a time. 1 = complete, 0 = pending,
 * -1 = invalid length. The returned payload view lasts until the next feed.
 * An invalid reader remains invalid until reset on a new connection. */
void b_frame_reset(b_frame_reader *reader);
int b_frame_feed(b_frame_reader *reader, uint8_t byte, size_t *length);
size_t b_frame_encode(const uint8_t *payload, size_t length,
                      uint8_t *output, size_t capacity);
