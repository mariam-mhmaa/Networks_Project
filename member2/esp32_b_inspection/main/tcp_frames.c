#include "tcp_frames.h"
#include <string.h>

void b_frame_reset(b_frame_reader *reader) {
    memset(reader, 0, sizeof(*reader));
}

int b_frame_feed(b_frame_reader *reader, uint8_t byte, size_t *length) {
    *length = 0;
    if (reader->invalid) return -1;
    if (reader->prefix_used < 4) {
        reader->prefix[reader->prefix_used++] = byte;
        if (reader->prefix_used == 4) {
            reader->expected = ((uint32_t)reader->prefix[0] << 24) |
                               ((uint32_t)reader->prefix[1] << 16) |
                               ((uint32_t)reader->prefix[2] << 8) |
                               reader->prefix[3];
            if (!reader->expected || reader->expected > B_PAYLOAD_MAX) {
                reader->invalid = true;
                return -1;
            }
        }
        return 0;
    }
    reader->payload[reader->used++] = byte;
    if (reader->used != reader->expected) return 0;
    *length = reader->used;
    reader->prefix_used = 0;
    reader->used = 0;
    reader->expected = 0;
    return 1;
}

size_t b_frame_encode(const uint8_t *payload, size_t length,
                      uint8_t *output, size_t capacity) {
    if (!payload || !output || !length || length > B_PAYLOAD_MAX ||
        capacity < length + 4) return 0;
    output[0] = (uint8_t)(length >> 24);
    output[1] = (uint8_t)(length >> 16);
    output[2] = (uint8_t)(length >> 8);
    output[3] = (uint8_t)length;
    memcpy(output + 4, payload, length);
    return length + 4;
}
