/* B transport adapter; lifecycle/parser implementation is shared with A. */
#include "inspection_protocol.h"
#include "../../../shared/station/station_protocol.c"
static bool tcp_send(const uint8_t *bytes, size_t length, void *context) {
    return b_tcp_queue(context, bytes, length);
}
void b_protocol_init(b_protocol *p, b_tcp_service *transport, const char *boot) {
    s_protocol_init(p, tcp_send, transport, boot, false, 500);
}
bool b_protocol_receive(const uint8_t *bytes, size_t length, void *context) {
    return s_protocol_receive(bytes, length, context);
}
void b_protocol_tick(b_protocol *p, uint64_t now) {
    b_tcp_service *transport = p->io;
    if (p->generation != transport->generation) {
        p->generation = transport->generation;
        p->next_heartbeat = 0;
    }
    s_protocol_tick(p, now);
}
