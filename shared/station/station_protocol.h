#pragma once
#include "station_app.h"
#define S_PAYLOAD_MAX 1024
typedef bool (*s_send_fn)(const uint8_t *, size_t, void *);
typedef struct {
    s_app app;
    s_send_fn send;
    void *io;
    uint64_t now_ms, next_heartbeat, heartbeat_no;
    uint32_t heartbeat_ms;
    uint32_t request_seq, output_seq;
    unsigned generation;
} s_protocol;
void s_protocol_init(s_protocol *, s_send_fn, void *, const char *, bool production, uint32_t heartbeat_ms);
bool s_protocol_receive(const uint8_t *, size_t, void *);
void s_protocol_tick(s_protocol *, uint64_t now_ms);
