/* Real serial service/framing/shared application; socket replaces UART only.
 * This is a native software test harness, not hardware evidence. */
#include <winsock2.h>
#include <windows.h>
#include <stdio.h>
#include <string.h>
#include "serial_service.h"
static a_serial serial;
static s_publish_fn original;
static bool drop_acks, drop_first_request, drop_completion, block_tx, drop_retirement, new_boot;
static bool filter(const s_app *app,const s_record *r,s_stage stage,void *context) {
    if (drop_retirement && r->request.action==S_RETIRE) return true;
    if (r->request.action==S_JOB &&
        ((drop_acks && (stage==S_RECEIVED || stage==S_ACCEPTED)) ||
         (drop_completion && stage==S_COMPLETED))) return true;
    if (r->request.action==S_JOB && block_tx) return false;
    return original(app,r,stage,context);
}
int main(int argc,char **argv) {
    for (int i=1;i<argc;++i) {
        if (!strcmp(argv[i],"--drop-acks")) drop_acks=true;
        else if (!strcmp(argv[i],"--drop-first-request")) drop_first_request=true;
        else if (!strcmp(argv[i],"--drop-completion")) drop_completion=true;
        else if (!strcmp(argv[i],"--block-tx")) block_tx=true;
        else if (!strcmp(argv[i],"--drop-retirement")) drop_retirement=true;
        else if (!strcmp(argv[i],"--new-boot")) new_boot=true;
        else return 2;
    }
    WSADATA data; if (WSAStartup(MAKEWORD(2,2),&data)) return 3;
    SOCKET listener=socket(AF_INET,SOCK_STREAM,IPPROTO_TCP);
    struct sockaddr_in addr; memset(&addr,0,sizeof(addr));
    addr.sin_family=AF_INET; addr.sin_addr.s_addr=htonl(INADDR_LOOPBACK);
    if (bind(listener,(struct sockaddr *)&addr,sizeof(addr)) || listen(listener,1)) return 4;
    int n=sizeof(addr); getsockname(listener,(struct sockaddr *)&addr,&n);
    printf("%u\n",(unsigned)ntohs(addr.sin_port)); fflush(stdout);
    SOCKET client=accept(listener,NULL,NULL); u_long nonblocking=1;
    ioctlsocket(client,FIONBIO,&nonblocking);
    a_serial_init(&serial,new_boot ? "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb" : "abcdef0123456789abcdef0123456789");
    original=serial.protocol.app.publish; serial.protocol.app.publish=filter;
    size_t offset=0;
    for (;;) {
        s_protocol_tick(&serial.protocol,GetTickCount64());
        uint8_t bytes[4096]; int got=recv(client,(char *)bytes,sizeof(bytes),0);
        if (!got) break;
        if (got>0) {
            if (drop_first_request) {
                /* Decode/filter whole records without changing retained firmware state. */
                static slip_decoder_t decoder;
                for (int i=0;i<got;++i) {
                    size_t length=0;
                    if (slip_feed(&decoder,bytes[i],&length)!=1 || !atr_validate(decoder.data,length)) continue;
                    decoder.data[length-2]=0; /* test-only bounded JSON substring check */
                    bool drop=strstr((char *)decoder.data+8,"\"type\":\"PRODUCE\"") && strstr((char *)decoder.data+8,"\"part_id\":1,");
                    uint16_t crc=atr_crc16(decoder.data,length-2);
                    decoder.data[length-2]=(uint8_t)(crc>>8); decoder.data[length-1]=(uint8_t)crc;
                    if (!drop) {
                        uint8_t encoded[SLIP_MAX_ENCODED]; size_t count=slip_encode(decoder.data,length,encoded,sizeof(encoded));
                        a_serial_receive(&serial,encoded,count);
                    }
                }
            } else a_serial_receive(&serial,bytes,(size_t)got);
        }
        const uint8_t *out; size_t length;
        if (a_serial_front(&serial,&out,&length)) {
            int sent=send(client,(const char *)out+offset,(int)(length-offset),0);
            if (sent>0) { offset+=(size_t)sent; if (offset==length) { a_serial_sent(&serial); offset=0; } }
        }
        Sleep(2);
    }
    closesocket(client); closesocket(listener); WSACleanup(); return 0;
}
