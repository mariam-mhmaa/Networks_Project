#include "production.h"
#include "esp_timer.h"
#include "history.h"
#include "esp_random.h"
#include "bootloader_random.h"
#include <stdbool.h>
#include <stdio.h>
#include <string.h>

/* Deliberately small flat JSON schema. No heap, recursive parsing or printf
 * on UART. ASCII identifiers are a documented subset of UTF-8 strings. */
typedef struct { char key[32], text[64], kind; uint32_t number; bool integer; } field_t;
typedef struct { const uint8_t *p, *end; } reader_t;
static production_send_fn send_event;
static uint32_t configured_ms;
static int64_t deadline_us;
static history_t history;
static char boot_id[33];
static int64_t next_heartbeat_us;
static uint32_t heartbeat_no;

static void ws(reader_t *r) {
    while (r->p < r->end && (*r->p == ' ' || *r->p == '\t' || *r->p == '\n' || *r->p == '\r')) ++r->p;
}
static bool take(reader_t *r, uint8_t c) {
    ws(r); if (r->p == r->end || *r->p != c) return false; ++r->p; return true;
}
static int hex(uint8_t c) {
    if (c >= '0' && c <= '9') return c-'0';
    if (c >= 'a' && c <= 'f') return c-'a'+10;
    if (c >= 'A' && c <= 'F') return c-'A'+10;
    return -1;
}
static bool string(reader_t *r, char *out, size_t capacity) {
    if (!take(r, '"')) return false;
    size_t used = 0;
    while (r->p < r->end) {
        unsigned c = *r->p++;
        if (c == '"') { out[used] = 0; return true; }
        if (c < 32 || c >= 127) return false; /* schema strings are ASCII */
        if (c == '\\') {
            if (r->p == r->end) return false;
            c = *r->p++;
            if (c == 'u') {
                c = 0;
                for (int i = 0; i < 4; ++i) {
                    if (r->p == r->end) return false;
                    int digit = hex(*r->p++); if (digit < 0) return false;
                    c = c * 16 + digit;
                }
                if (!c || c >= 127) return false;
            } else if (c == 'b') c = '\b';
            else if (c == 'f') c = '\f';
            else if (c == 'n') c = '\n';
            else if (c == 'r') c = '\r';
            else if (c == 't') c = '\t';
            else if (c != '"' && c != '\\' && c != '/') return false;
        }
        if (used + 1 >= capacity) return false;
        out[used++] = (char)c;
    }
    return false;
}
static bool value(reader_t *r, field_t *f) {
    ws(r); if (r->p == r->end) return false;
    if (*r->p == '"') { f->kind = 's'; return string(r, f->text, sizeof(f->text)); }
    const uint8_t *start = r->p;
    while (r->p < r->end && *r->p != ',' && *r->p != '}' &&
           *r->p != ' ' && *r->p != '\r' && *r->p != '\n' && *r->p != '\t') ++r->p;
    size_t n = r->p - start;
    if ((n == 4 && (!memcmp(start,"true",4) || !memcmp(start,"null",4))) ||
        (n == 5 && !memcmp(start,"false",5))) { f->kind='b'; return true; }
    /* Strict JSON number grammar; only unsigned integer syntax is usable. */
    const uint8_t *p = start, *end = r->p;
    f->kind='n'; f->integer=true; f->number=0;
    if (p < end && *p == '-') { f->integer=false; ++p; }
    const uint8_t *digits = p;
    if (p == end || *p < '0' || *p > '9') return false;
    if (*p == '0') ++p;
    else while (p < end && *p >= '0' && *p <= '9') ++p;
    for (const uint8_t *d=digits; d<p; ++d) {
        if (f->number > (UINT32_MAX-(*d-'0'))/10) f->integer=false;
        if (f->integer) f->number=f->number*10+(*d-'0');
    }
    if (p < end && *p == '.') {
        f->integer=false; ++p; const uint8_t *first=p;
        while (p < end && *p >= '0' && *p <= '9') ++p;
        if (p == first) return false;
    }
    if (p < end && (*p == 'e' || *p == 'E')) {
        f->integer=false; ++p;
        if (p < end && (*p == '+' || *p == '-')) ++p;
        const uint8_t *first=p;
        while (p < end && *p >= '0' && *p <= '9') ++p;
        if (p == first) return false;
    }
    return p == end;
}
static int parse(const uint8_t *data, size_t length, field_t fields[8]) {
    reader_t r={data,data+length}; int count=0;
    if (!take(&r,'{')) return -1;
    ws(&r);
    if (r.p < r.end && *r.p == '}') { ++r.p; ws(&r); return r.p==r.end ? 0 : -1; }
    do {
        if (count == 8 || !string(&r,fields[count].key,sizeof(fields[count].key)) ||
            !take(&r,':') || !value(&r,&fields[count])) return -1;
        for (int i=0; i<count; ++i) if (!strcmp(fields[i].key,fields[count].key)) return -1;
        ++count; ws(&r);
        if (r.p == r.end) return -1;
        if (*r.p == '}') { ++r.p; ws(&r); return r.p==r.end ? count : -1; }
    } while (take(&r,','));
    return -1;
}
static field_t *find(field_t *f, int count, const char *key) {
    for (int i=0; i<count; ++i) if (!strcmp(f[i].key,key)) return &f[i];
    return NULL;
}
static bool id(field_t *f) {
    if (!f || f->kind != 's' || !f->text[0] || strlen(f->text)>48) return false;
    for (const char *p=f->text; *p; ++p)
        if (!((*p>='a' && *p<='z') || (*p>='A' && *p<='Z') || (*p>='0' && *p<='9') ||
              *p=='_' || *p=='-' || *p=='.' || *p==':')) return false;
    return true;
}
static bool positive(field_t *f, uint32_t limit) {
    return f && f->kind=='n' && f->integer && f->number>0 && f->number<=limit;
}
static void emit(uint32_t seq, const char *type, const char *identifiers, const char *extra) {
    char json[512];
    int n=snprintf(json,sizeof(json),"{\"type\":\"%s\",\"boot_id\":\"%s\",%s%s}",type,boot_id,identifiers,extra);
    if (n>0 && n<(int)sizeof(json)) send_event(seq,json,(size_t)n);
}
void production_init(production_send_fn send) {
    send_event=send; configured_ms=0; deadline_us=0;
    memset(&history,0,sizeof(history));
    uint8_t random[16];
    /* No RF/ADC users in this application. Enable physical entropy explicitly. */
    bootloader_random_enable();
    esp_fill_random(random,sizeof(random));
    bootloader_random_disable();
    for (size_t i=0;i<sizeof(random);++i) snprintf(boot_id+i*2,3,"%02x",random[i]);
    next_heartbeat_us=esp_timer_get_time()+1000000;
    heartbeat_no=0;
}
static void status_event(uint32_t seq, const char *type) {
    char fields[240], active[24];
    if (history.active_valid) snprintf(active,sizeof(active),"%lu",(unsigned long)history.active.request.op_no);
    else strcpy(active,"null");
    if (!strcmp(type,"HEARTBEAT")) ++heartbeat_no;
    snprintf(fields,sizeof(fields),"\"state\":\"%s\",\"active_op_no\":%s,\"high_water\":%lu,\"production_time_ms\":%lu,\"heartbeat_no\":%lu",
             history.active_valid ? "PRODUCING" : configured_ms ? "IDLE" : "UNCONFIGURED",
             active,(unsigned long)history.high_water,(unsigned long)configured_ms,(unsigned long)heartbeat_no);
    emit(seq,type,fields,"");
}
static void identifiers_for(const operation_t *op, char *out, size_t capacity) {
    if (op->kind==OP_CONFIGURE)
        snprintf(out,capacity,"\"op_no\":%lu,\"cmd_id\":\"%s\"",(unsigned long)op->op_no,op->id);
    else
        snprintf(out,capacity,"\"op_no\":%lu,\"job_id\":\"%s\",\"batch_id\":\"%s\",\"part_id\":%lu",
                 (unsigned long)op->op_no,op->id,op->batch_id,(unsigned long)op->part_id);
}
static void completed_event(uint32_t seq, const result_t *result, bool replayed) {
    char identifiers[240], extra[100];
    identifiers_for(&result->request,identifiers,sizeof(identifiers));
    if (result->request.kind==OP_CONFIGURE)
        snprintf(extra,sizeof(extra),",\"production_time_ms\":%lu,\"replayed\":%s",
                 (unsigned long)result->applied_ms,replayed ? "true" : "false");
    else snprintf(extra,sizeof(extra),",\"replayed\":%s",replayed ? "true" : "false");
    emit(seq,result->request.kind==OP_CONFIGURE ? "PRODUCTION_CONFIGURED" : "PART_PRODUCED",identifiers,extra);
}
void production_request(uint32_t seq, const uint8_t *payload, size_t length) {
    field_t fields[8]={0}; int n=parse(payload,length,fields);
    if (n<0) return; /* No trusted application identity. */
    field_t *type=find(fields,n,"type"), *cmd=find(fields,n,"cmd_id"), *job=find(fields,n,"job_id");
    field_t *batch=find(fields,n,"batch_id"), *part=find(fields,n,"part_id");
    bool config=type && type->kind=='s' && !strcmp(type->text,"CONFIGURE_PRODUCTION");
    bool produce=type && type->kind=='s' && !strcmp(type->text,"PRODUCE_PART");
    if (type && type->kind=='s' && !strcmp(type->text,"GET_STATUS")) {
        if (n==1) status_event(seq,"STATUS");
        return; /* No operation number, settings or history mutation. */
    }
    char identifiers[240];
    if (produce && id(job) && id(batch)) {
        snprintf(identifiers,sizeof(identifiers),"\"job_id\":\"%s\",\"batch_id\":\"%s\"",job->text,batch->text);
        if (positive(part,2147483647)) {
            size_t used=strlen(identifiers);
            snprintf(identifiers+used,sizeof(identifiers)-used,",\"part_id\":%lu",(unsigned long)part->number);
        }
    } else if (id(cmd)) {
        snprintf(identifiers,sizeof(identifiers),"\"cmd_id\":\"%s\"",cmd->text);
    } else return; /* Invalid/unusable IDs: silent, no production. */
    field_t *ms=find(fields,n,"production_time_ms");
    field_t *number=find(fields,n,"op_no");
    field_t *session=find(fields,n,"boot_id");
    const char *reason=NULL;
    if (!session || session->kind!='s' || strcmp(session->text,boot_id)) reason="SESSION_MISMATCH";
    if (!reason && config) {
        if (!id(cmd) || (n!=5 && n!=4) || !positive(ms,60000)) reason="INVALID_CONFIGURATION";
    } else if (!reason && produce) {
        if (!id(job) || !id(batch) || (n!=6 && n!=5) || !positive(part,2147483647)) reason="INVALID_JOB";
    } else if (!reason) reason="UNKNOWN_COMMAND";
    if (!reason && !positive(number,UINT32_MAX)) reason="INVALID_OPERATION_NUMBER";
    operation_t op={0};
    if (!reason) {
        op.op_no=number->number; op.kind=config ? OP_CONFIGURE : OP_PRODUCE;
        strcpy(op.id,config ? cmd->text : job->text);
        if (config) op.requested_ms=ms->number;
        else { strcpy(op.batch_id,batch->text); op.part_id=part->number; }
        if (!operation_id_matches(&op)) reason="INVALID_OPERATION_ID";
        else if (n!=(config ? 5 : 6)) reason=config ? "INVALID_CONFIGURATION" : "INVALID_JOB";
    }
    /* RECEIVED includes a usable op_no even for semantic rejections. */
    if (positive(number,UINT32_MAX)) {
        size_t used=strlen(identifiers);
        snprintf(identifiers+used,sizeof(identifiers)-used,",\"op_no\":%lu",(unsigned long)number->number);
    }
    emit(seq,"RECEIVED",identifiers,"");
    const result_t *match=NULL;
    history_decision_t decision=HISTORY_NEW;
    if (!reason) {
        decision=history_lookup(&history,&op,&match);
        if (decision==HISTORY_CONFLICT) reason="OPERATION_CONFLICT";
        else if (decision==HISTORY_STALE) reason="STALE_RESULT_UNAVAILABLE";
        else if (decision==HISTORY_NEW && history.active_valid) reason="BUSY";
        else if (decision==HISTORY_NEW && produce && !configured_ms) reason="NOT_CONFIGURED";
    }
    if (reason) {
        char extra[96]; snprintf(extra,sizeof(extra),",\"reason\":\"%s\"",reason);
        emit(seq,"REJECTED",identifiers,extra); return;
    }
    if (decision==HISTORY_ACTIVE) {
        emit(seq,"OPERATION_RUNNING",identifiers,""); return;
    }
    if (decision==HISTORY_COMPLETED) { completed_event(seq,match,true); return; }
    /* Commit identity/high-water BEFORE configuration or timer side effects. */
    if (!history_accept(&history,&op,seq,config ? op.requested_ms : configured_ms)) return;
    emit(seq,"ACCEPTED",identifiers,"");
    if (config) {
        configured_ms=op.requested_ms;
        completed_event(seq,&history.active,false);
        history_complete(&history);
    } else {
        deadline_us=esp_timer_get_time()+(int64_t)configured_ms*1000;
    }
}
void production_poll(void) {
    int64_t now=esp_timer_get_time();
    if (history.active_valid && now>=deadline_us) {
        completed_event(history.active.seq,&history.active,false);
        history_complete(&history);
    }
    if (now>=next_heartbeat_us) {
        next_heartbeat_us=now+1000000;
        status_event(0,"HEARTBEAT");
    }
}
