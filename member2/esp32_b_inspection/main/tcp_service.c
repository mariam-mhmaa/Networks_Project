#include "tcp_service.h"
#include <string.h>
#ifdef _WIN32
#include <ws2tcpip.h>
typedef int b_socklen;
static int socket_error(void) { return WSAGetLastError(); }
static bool would_wait(int error) { return error == WSAEWOULDBLOCK || error == WSAEINTR; }
static void close_socket(b_socket sock) { closesocket(sock); }
static bool nonblocking(b_socket sock) { u_long flag = 1; return ioctlsocket(sock, FIONBIO, &flag) == 0; }
#else
#include <errno.h>
#include <fcntl.h>
#include <unistd.h>
#include "lwip/sockets.h"
typedef socklen_t b_socklen;
static int socket_error(void) { return errno; }
static bool would_wait(int error) { return error == EAGAIN || error == EWOULDBLOCK || error == EINTR; }
static void close_socket(b_socket sock) { close(sock); }
static bool nonblocking(b_socket sock) {
    int flags = fcntl(sock, F_GETFL, 0);
    return flags >= 0 && fcntl(sock, F_SETFL, flags | O_NONBLOCK) == 0;
}
#endif

static void drop_client(b_tcp_service *service) {
    if (service->client != B_INVALID_SOCKET) close_socket(service->client);
    service->client = B_INVALID_SOCKET;
    service->head = service->count = 0;
    service->read_closed = false;
    b_frame_reset(&service->reader);
}

void b_tcp_init(b_tcp_service *service, b_frame_handler handler, void *context) {
    memset(service, 0, sizeof(*service));
    service->listener = service->client = B_INVALID_SOCKET;
    service->handler = handler;
    service->context = context;
}

void b_tcp_close(b_tcp_service *service) {
    drop_client(service);
    if (service->listener != B_INVALID_SOCKET) close_socket(service->listener);
    service->listener = B_INVALID_SOCKET;
}

bool b_tcp_open(b_tcp_service *service, uint32_t address_nbo, uint16_t port) {
    struct sockaddr_in address;
    int reuse = 1;
    b_tcp_close(service);
    service->listener = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
    if (service->listener == B_INVALID_SOCKET) return false;
    if (setsockopt(service->listener, SOL_SOCKET, SO_REUSEADDR,
                   (const char *)&reuse, sizeof(reuse)) != 0) goto failed;
    memset(&address, 0, sizeof(address));
    address.sin_family = AF_INET;
    address.sin_port = htons(port);
    address.sin_addr.s_addr = address_nbo;
    if (!nonblocking(service->listener) ||
        bind(service->listener, (struct sockaddr *)&address, sizeof(address)) != 0 ||
        listen(service->listener, 2) != 0) goto failed;
    return true;
failed:
    b_tcp_close(service);
    return false;
}

bool b_tcp_queue(b_tcp_service *service, const uint8_t *payload, size_t length) {
    if (service->client == B_INVALID_SOCKET || service->count == B_TX_SLOTS) return false;
    unsigned slot = (service->head + service->count) % B_TX_SLOTS;
    b_tx_frame *frame = &service->tx[slot];
    size_t encoded = b_frame_encode(payload, length, frame->bytes, sizeof(frame->bytes));
    if (!encoded) return false;
    frame->length = encoded;
    frame->sent = 0;
    ++service->count;
    return true;
}

void b_tcp_poll(b_tcp_service *service) {
    if (service->listener == B_INVALID_SOCKET) return;
    /* Accept once per turn. A second peer never replaces the active owner. */
    b_socket candidate = accept(service->listener, NULL, NULL);
    if (candidate != B_INVALID_SOCKET) {
        if (service->client != B_INVALID_SOCKET || !nonblocking(candidate)) {
            close_socket(candidate);
        } else {
            service->client = candidate;
            ++service->generation;
            b_frame_reset(&service->reader);
        }
    }
    if (service->client == B_INVALID_SOCKET) return;

    /* Each turn has a finite receive budget; a busy peer cannot starve
     * inspection timers/control work elsewhere in the application. */
    for (unsigned turn = 0; turn < 4 && !service->read_closed; ++turn) {
        uint8_t bytes[256];
        int received = recv(service->client, (char *)bytes, sizeof(bytes), 0);
        if (received == 0) { service->read_closed = true; break; }
        if (received < 0) {
            if (!would_wait(socket_error())) drop_client(service);
            break;
        }
        for (int i = 0; i < received; ++i) {
            size_t length = 0;
            int result = b_frame_feed(&service->reader, bytes[i], &length);
            if (result < 0 || (result == 1 && service->handler &&
                !service->handler(service->reader.payload, length, service->context))) {
                drop_client(service);
                return;
            }
        }
    }
    if (service->client == B_INVALID_SOCKET) return;
    if (!service->count) {
        if (service->read_closed) drop_client(service);
        return;
    }
    b_tx_frame *frame = &service->tx[service->head];
    int sent = send(service->client, (const char *)frame->bytes + frame->sent,
                    (int)(frame->length - frame->sent), 0);
    if (sent < 0) {
        if (!would_wait(socket_error())) drop_client(service);
    } else if (sent == 0) {
        drop_client(service);
    } else {
        frame->sent += (size_t)sent;
        if (frame->sent == frame->length) {
            service->head = (service->head + 1) % B_TX_SLOTS;
            --service->count;
            if (!service->count && service->read_closed) drop_client(service);
        }
    }
}
