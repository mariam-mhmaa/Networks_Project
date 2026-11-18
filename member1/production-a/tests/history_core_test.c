#include "history.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>

static operation_t config(uint32_t n, uint32_t ms) {
    operation_t op={0}; op.op_no=n; op.kind=OP_CONFIGURE; op.requested_ms=ms;
    snprintf(op.id,sizeof(op.id),"cfg:%lu",(unsigned long)n); return op;
}
int main(void) {
    history_t h={0}; const result_t *match=NULL;
    operation_t op=config(1,1000);
    assert(operation_id_matches(&op));
    strcpy(op.id,"cfg:01"); assert(!operation_id_matches(&op));
    strcpy(op.id,"cfg"); assert(!operation_id_matches(&op));
    strcpy(op.id,"cfg:2"); assert(!operation_id_matches(&op));
    op=config(UINT32_MAX,1); assert(operation_id_matches(&op));
    op=config(1,1000);
    assert(history_lookup(&h,&op,&match)==HISTORY_NEW);
    assert(history_accept(&h,&op,111,1000));
    assert(h.high_water==1 && h.count==0 && h.active_valid);
    assert(history_lookup(&h,&op,&match)==HISTORY_ACTIVE && match->seq==111);
    operation_t conflict=op; conflict.requested_ms=2500;
    assert(history_lookup(&h,&conflict,&match)==HISTORY_CONFLICT);
    operation_t next=config(3,2500);
    assert(!history_accept(&h,&next,222,2500) && h.high_water==1);
    history_complete(&h);
    assert(history_lookup(&h,&op,&match)==HISTORY_COMPLETED && match->applied_ms==1000);
    assert(history_accept(&h,&next,222,2500)); history_complete(&h);
    assert(history_lookup(&h,&op,&match)==HISTORY_COMPLETED && match->applied_ms==1000);
    operation_t gap=config(2,1000);
    assert(history_lookup(&h,&gap,&match)==HISTORY_STALE);
    assert(history_lookup(&h,&conflict,&match)==HISTORY_CONFLICT);
    for (uint32_t n=4;n<=12;++n) {
        operation_t work=config(n,n);
        assert(history_accept(&h,&work,n,n)); history_complete(&h);
    }
    assert(h.count==8 && h.high_water==12);
    assert(history_lookup(&h,&op,&match)==HISTORY_STALE);
    next=config(13,13); assert(history_accept(&h,&next,13,13));
    /* Active is independent of eight completed records. */
    assert(h.active_valid && h.count==8 && h.active.request.op_no==13);
    assert(history_lookup(&h,&next,&match)==HISTORY_ACTIVE);
    history_complete(&h);
    operation_t reused=op; reused.op_no=14;
    assert(!operation_id_matches(&reused));
    memset(&h,0,sizeof(h));
    assert(history_lookup(&h,&op,&match)==HISTORY_NEW); /* Honest restart limit. */
    printf("PASS: C history decisions, suffixes, conflicts, gaps, replacement, active isolation, reset\n");
    printf("sizeof(operation_t)=%u sizeof(result_t)=%u sizeof(history_t)=%u\n",
           (unsigned)sizeof(operation_t),(unsigned)sizeof(result_t),(unsigned)sizeof(history_t));
    return 0;
}
