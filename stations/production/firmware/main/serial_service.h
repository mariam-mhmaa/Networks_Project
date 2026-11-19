#pragma once
#include "protocol.h"
#include "../../../../shared/station/station_protocol.h"
#define A_TX_SLOTS 4
typedef struct {
    uint8_t data[A_TX_SLOTS][SLIP_MAX_ENCODED];
    size_t length[A_TX_SLOTS];
    unsigned head, count;
    s_protocol protocol;
    slip_decoder_t decoder;
} a_serial;
void a_serial_init(a_serial *, const char *boot);
void a_serial_receive(a_serial *, const uint8_t *, size_t);
bool a_serial_front(a_serial *, const uint8_t **, size_t *);
void a_serial_sent(a_serial *);
