#pragma once
#include "inspection_app.h"
#include "tcp_service.h"
#include "../../../shared/station/station_protocol.h"
typedef s_protocol b_protocol;
void b_protocol_init(b_protocol *, b_tcp_service *, const char *);
bool b_protocol_receive(const uint8_t *, size_t, void *);
void b_protocol_tick(b_protocol *, uint64_t);
