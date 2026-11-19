/* Same application/protocol/framing/socket C as ESP32; only clock and
 * SHA256 backend are platform-specific. Fault switches are test-only. */
#include "inspection_protocol.h"
#include <stdio.h>
#include <string.h>
#include <windows.h>

static b_protocol protocol;
static b_tcp_service transport;
static b_publish_fn original_publish;
static bool drop_receipt, drop_acceptance, drop_completion, block_inspection_tx;
static bool drop_configuration, drop_close, drop_first_request;
static bool conflicting_completion;
static bool filter(const b_app *app, const b_record *r, b_stage stage, void *context) {
    if (conflicting_completion && r->request.action == B_INSPECT && stage == B_COMPLETED) {
        bool ok = original_publish(app, r, stage, context);
        b_record conflicting = *r;
        conflicting.fail = !r->fail;
        (void)original_publish(app, &conflicting, stage, context);
        return ok;
    }
    if ((r->request.action == B_CONFIGURE && drop_configuration) ||
        (r->request.action == B_CLOSE && drop_close)) return true;
    if (r->request.action == B_INSPECT && block_inspection_tx) return false;
    if (r->request.action == B_INSPECT &&
        ((stage == B_RECEIVED && drop_receipt) ||
         (stage == B_ACCEPTED && drop_acceptance) ||
         (stage == B_COMPLETED && drop_completion))) return true;
    return original_publish(app, r, stage, context);
}
static bool receive_app(const uint8_t *bytes, size_t length, void *context) {
    char json[B_PAYLOAD_MAX+1];
    if (length > B_PAYLOAD_MAX) return false;
    memcpy(json,bytes,length); json[length]=0;
    if (drop_first_request && strstr(json,"\"type\":\"INSPECT\"") && strstr(json,"\"part_id\":1,")) return true;
    return b_protocol_receive(bytes,length,context);
}
int main(int argc, char **argv) {
    for (int i = 1; i < argc; ++i) {
        if (!strcmp(argv[i], "--drop-receipt")) drop_receipt = true;
        else if (!strcmp(argv[i], "--drop-acceptance")) drop_acceptance = true;
        else if (!strcmp(argv[i], "--drop-completion")) drop_completion = true;
        else if (!strcmp(argv[i], "--block-inspection-tx")) block_inspection_tx = true;
        else if (!strcmp(argv[i], "--drop-configuration")) drop_configuration = true;
        else if (!strcmp(argv[i], "--drop-close")) drop_close = true;
        else if (!strcmp(argv[i], "--drop-first-request")) drop_first_request = true;
        else if (!strcmp(argv[i], "--conflicting-completion")) conflicting_completion = true;
        else return 2;
    }
    WSADATA data;
    if (WSAStartup(MAKEWORD(2, 2), &data)) return 3;
    b_tcp_init(&transport, receive_app, &protocol);
    b_protocol_init(&protocol, &transport, "0123456789abcdef0123456789abcdef");
    original_publish = protocol.app.publish;
    protocol.app.publish = filter;
    if (!b_tcp_open(&transport, htonl(INADDR_LOOPBACK), 0)) return 4;
    struct sockaddr_in address;
    int size = sizeof(address);
    if (getsockname(transport.listener, (struct sockaddr *)&address, &size)) return 5;
    printf("%u\n", (unsigned)ntohs(address.sin_port)); fflush(stdout);
    for (;;) {
        b_protocol_tick(&protocol, GetTickCount64());
        b_tcp_poll(&transport);
        Sleep(2);
    }
}
