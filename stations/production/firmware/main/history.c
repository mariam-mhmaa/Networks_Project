#include "history.h"
#include <stdio.h>
#include <string.h>

bool operation_id_matches(const operation_t *op) {
    if (!op->op_no) return false;
    const char *suffix=strrchr(op->id, ':');
    if (!suffix || suffix==op->id) return false;
    char canonical[12];
    snprintf(canonical,sizeof(canonical),":%lu",(unsigned long)op->op_no);
    return !strcmp(suffix,canonical);
}
bool operation_equal(const operation_t *a, const operation_t *b) {
    return a->op_no==b->op_no && a->kind==b->kind && a->part_id==b->part_id &&
           a->requested_ms==b->requested_ms && !strcmp(a->id,b->id) && !strcmp(a->batch_id,b->batch_id);
}
history_decision_t history_lookup(const history_t *h, const operation_t *op, const result_t **match) {
    *match=NULL;
    if (h->active_valid && h->active.request.op_no==op->op_no) {
        *match=&h->active;
        return operation_equal(op,&h->active.request) ? HISTORY_ACTIVE : HISTORY_CONFLICT;
    }
    for (uint32_t i=0; i<h->count; ++i) {
        if (h->completed[i].request.op_no==op->op_no) {
            *match=&h->completed[i];
            return operation_equal(op,&h->completed[i].request) ? HISTORY_COMPLETED : HISTORY_CONFLICT;
        }
    }
    return op->op_no<=h->high_water ? HISTORY_STALE : HISTORY_NEW;
}
bool history_accept(history_t *h, const operation_t *op, uint32_t seq, uint32_t applied_ms) {
    if (h->active_valid || op->op_no<=h->high_water || !operation_id_matches(op)) return false;
    h->active.request=*op;
    h->active.seq=seq;
    h->active.applied_ms=applied_ms;
    h->active_valid=true;
    h->high_water=op->op_no;
    return true;
}
void history_complete(history_t *h) {
    if (!h->active_valid) return;
    h->completed[h->next]=h->active;
    h->next=(h->next+1)%HISTORY_CAPACITY;
    if (h->count<HISTORY_CAPACITY) ++h->count;
    h->active_valid=false;
}
