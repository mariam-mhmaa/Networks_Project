#include "serial_service.h"
#include <string.h>
static bool queue_record(a_serial *s, const uint8_t *record, size_t length) {
    if (s->count == A_TX_SLOTS) return false;
    unsigned tail = (s->head + s->count) % A_TX_SLOTS;
    size_t n = slip_encode(record, length, s->data[tail], sizeof(s->data[tail]));
    if (!n) return false;
    s->length[tail] = n; ++s->count;
    return true;
}
static bool send_json(const uint8_t *bytes, size_t length, void *context) {
    a_serial *s = context;
    uint8_t record[ATR_MAX_DECODED];
    if (length > ATR_MAX_PAYLOAD || s->count == A_TX_SLOTS) return false;
    record[0] = record[1] = 0;
    uint32_t seq = s->protocol.output_seq;
    for (unsigned i = 0; i < 4; ++i) record[2+i] = (uint8_t)(seq >> (24-i*8));
    record[6] = (uint8_t)(length >> 8); record[7] = (uint8_t)length;
    memcpy(record+8, bytes, length);
    uint16_t crc = atr_crc16(record, length+8);
    record[length+8] = (uint8_t)(crc >> 8); record[length+9] = (uint8_t)crc;
    return queue_record(s, record, length+10);
}
void a_serial_init(a_serial *s, const char *boot) {
    memset(s, 0, sizeof(*s));
    s_protocol_init(&s->protocol, send_json, s, boot, true, 1000);
}
void a_serial_receive(a_serial *s, const uint8_t *bytes, size_t size) {
    for (size_t i = 0; i < size; ++i) {
        size_t length = 0;
        if (slip_feed(&s->decoder, bytes[i], &length) != 1) continue;
        uint8_t *r = s->decoder.data;
        if (!atr_validate(r, length)) continue;
        if (r[0] == 0 && r[1] == 0) {
            s->protocol.request_seq = ((uint32_t)r[2]<<24)|((uint32_t)r[3]<<16)|((uint32_t)r[4]<<8)|r[5];
            if (s->protocol.request_seq) (void)s_protocol_receive(r+8, length-10, &s->protocol);
        } else {
            /* Preserve the contributor's nonzero-test-ID XOR regression path. */
            for (size_t j = 8; j < length-2; ++j) r[j] ^= 0xa5;
            uint16_t crc = atr_crc16(r, length-2);
            r[length-2] = (uint8_t)(crc>>8); r[length-1] = (uint8_t)crc;
            (void)queue_record(s, r, length);
        }
    }
}
bool a_serial_front(a_serial *s, const uint8_t **bytes, size_t *length) {
    if (!s->count) return false;
    *bytes = s->data[s->head]; *length = s->length[s->head]; return true;
}
void a_serial_sent(a_serial *s) {
    if (s->count) { s->head = (s->head+1)%A_TX_SLOTS; --s->count; }
}
