#pragma once
#include "inspection_app.h"
#include "tcp_service.h"

typedef struct {
    b_app app;
    b_tcp_service *transport;
    uint64_t now_ms, next_heartbeat;
    unsigned generation;
} b_protocol;

void b_protocol_init(b_protocol *, b_tcp_service *, const char *boot_id);
bool b_protocol_receive(const uint8_t *, size_t, void *);
void b_protocol_tick(b_protocol *, uint64_t now_ms);
