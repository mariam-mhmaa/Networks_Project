/* Native host harness for the actual firmware transport modules.
 * Echo exists ONLY in this test binary, never in production firmware. */
#include "tcp_service.h"
#include <stdio.h>
#include <string.h>
#include <windows.h>

#define CHECK(test) do { if (!(test)) { fprintf(stderr, "Failed line %d: %s\n", __LINE__, #test); return 1; } } while (0)

static int unit_checks(void) {
    b_frame_reader reader;
    uint8_t frame[B_FRAME_MAX], data[B_PAYLOAD_MAX];
    size_t length = 0;
    for (size_t i = 0; i < sizeof(data); ++i) data[i] = (uint8_t)i;
    CHECK(b_frame_encode(data, sizeof(data), frame, sizeof(frame)) == B_FRAME_MAX);
    CHECK(frame[0] == 0 && frame[1] == 0 && frame[2] == 4 && frame[3] == 0);
    b_frame_reset(&reader);
    for (size_t i = 0; i < sizeof(frame); ++i)
        CHECK(b_frame_feed(&reader, frame[i], &length) == (i + 1 == sizeof(frame) ? 1 : 0));
    CHECK(length == sizeof(data) && memcmp(reader.payload, data, sizeof(data)) == 0);
    CHECK(b_frame_encode(data, 0, frame, sizeof(frame)) == 0);
    CHECK(b_frame_encode(data, B_PAYLOAD_MAX + 1, frame, sizeof(frame)) == 0);
    CHECK(b_frame_encode(data, 1, frame, 4) == 0);
    CHECK(b_frame_encode(NULL, 1, frame, sizeof(frame)) == 0);
    /* Every possible two-chunk split of a complete frame. */
    size_t n = b_frame_encode(data, 17, frame, sizeof(frame));
    for (size_t split = 0; split <= n; ++split) {
        b_frame_reset(&reader);
        unsigned complete = 0;
        for (size_t i = 0; i < split; ++i) complete += b_frame_feed(&reader, frame[i], &length) == 1;
        for (size_t i = split; i < n; ++i) complete += b_frame_feed(&reader, frame[i], &length) == 1;
        CHECK(complete == 1 && length == 17 && memcmp(reader.payload, data, 17) == 0);
    }
    b_frame_reset(&reader);
    for (unsigned repeat = 0; repeat < 3; ++repeat) {
        for (size_t i = 0; i < n; ++i) CHECK(b_frame_feed(&reader, frame[i], &length) == (i + 1 == n ? 1 : 0));
        CHECK(length == 17);
    }
    const uint8_t bad[][4] = {{0,0,0,0}, {0,0,4,1}, {255,255,255,255}};
    for (unsigned k = 0; k < 3; ++k) {
        b_frame_reset(&reader);
        for (unsigned i = 0; i < 4; ++i) CHECK(b_frame_feed(&reader, bad[k][i], &length) == (i == 3 ? -1 : 0));
        CHECK(b_frame_feed(&reader, 1, &length) == -1);
    }
    b_frame_reset(&reader);
    CHECK(b_frame_feed(&reader, frame[0], &length) == 0);
    b_frame_reset(&reader);
    for (size_t i = 0; i < n; ++i) CHECK(b_frame_feed(&reader, frame[i], &length) == (i + 1 == n ? 1 : 0));

    b_tcp_service service;
    b_tcp_init(&service, NULL, NULL);
    CHECK(!b_tcp_queue(&service, data, 1));
    service.client = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
    CHECK(service.client != B_INVALID_SOCKET);
    for (unsigned i = 0; i < B_TX_SLOTS; ++i) CHECK(b_tcp_queue(&service, data, 17));
    CHECK(!b_tcp_queue(&service, data, 17));
    data[0] = 99;
    CHECK(service.tx[0].bytes[4] == 0); /* Queue owns a copy. */
    b_tcp_close(&service);
    CHECK(service.count == 0 && service.client == B_INVALID_SOCKET);
    puts("Native codec, reset, bounds and bounded-TX checks passed");
    return 0;
}

static bool echo_frame(const uint8_t *data, size_t length, void *context) {
    return b_tcp_queue((b_tcp_service *)context, data, length);
}

int main(int argc, char **argv) {
    WSADATA startup;
    if (WSAStartup(MAKEWORD(2, 2), &startup)) return 2;
    if (argc > 1 && !strcmp(argv[1], "--unit")) {
        int result = unit_checks();
        WSACleanup();
        return result;
    }
    static b_tcp_service service;
    b_tcp_init(&service, echo_frame, &service);
    if (!b_tcp_open(&service, htonl(INADDR_LOOPBACK), 0)) return 3;
    struct sockaddr_in address;
    int address_size = sizeof(address);
    if (getsockname(service.listener, (struct sockaddr *)&address, &address_size)) return 4;
    setvbuf(stdout, NULL, _IONBF, 0);
    printf("%u\n", (unsigned)ntohs(address.sin_port));
    ULONGLONG until = GetTickCount64() + 20000;
    while (GetTickCount64() < until) { b_tcp_poll(&service); Sleep(1); }
    b_tcp_close(&service);
    WSACleanup();
    return 0;
}
