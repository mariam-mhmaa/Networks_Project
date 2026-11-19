#pragma once
#include <stddef.h>
#include <stdint.h>
typedef void (*production_send_fn)(uint32_t seq, const char *json, size_t length);
void production_init(production_send_fn send);
void production_request(uint32_t seq, const uint8_t *payload, size_t length);
void production_poll(void);
