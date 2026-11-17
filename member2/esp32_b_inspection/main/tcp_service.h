#pragma once
#include "tcp_frames.h"

#ifdef _WIN32
#include <winsock2.h>
typedef SOCKET b_socket;
#define B_INVALID_SOCKET INVALID_SOCKET
#else
typedef int b_socket;
#define B_INVALID_SOCKET (-1)
#endif

#define B_TX_SLOTS 4u
typedef bool (*b_frame_handler)(const uint8_t *, size_t, void *);
typedef struct { uint8_t bytes[B_FRAME_MAX]; size_t length, sent; } b_tx_frame;

typedef struct {
    b_socket listener, client;
    b_frame_reader reader;
    b_tx_frame tx[B_TX_SLOTS];
    unsigned head, count;
    bool read_closed;
    b_frame_handler handler;
    void *context;
} b_tcp_service;

void b_tcp_init(b_tcp_service *service, b_frame_handler handler, void *context);
/* address_nbo is an IPv4 address in network byte order; port is host order. */
bool b_tcp_open(b_tcp_service *service, uint32_t address_nbo, uint16_t port);
void b_tcp_close(b_tcp_service *service);
/* Bounded, nonblocking work only. Call regularly from the network owner. */
void b_tcp_poll(b_tcp_service *service);
/* Copies a frame; false means disconnected/full/invalid, never a blocking wait.
 * The application must retain terminal results independently of this queue. */
bool b_tcp_queue(b_tcp_service *service, const uint8_t *payload, size_t length);
