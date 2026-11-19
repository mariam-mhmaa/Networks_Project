#pragma once
#include <stdbool.h>
#include <stdint.h>
#define HISTORY_CAPACITY 8
enum { OP_CONFIGURE=1, OP_PRODUCE=2 };
typedef struct {
    uint32_t op_no, kind, part_id, requested_ms;
    char id[49], batch_id[49];
} operation_t;
typedef struct {
    operation_t request;
    uint32_t seq, applied_ms;
} result_t;
typedef struct {
    result_t completed[HISTORY_CAPACITY];
    result_t active;
    uint32_t high_water, next, count;
    bool active_valid;
} history_t;
typedef enum { HISTORY_NEW, HISTORY_ACTIVE, HISTORY_COMPLETED,
               HISTORY_CONFLICT, HISTORY_STALE } history_decision_t;
bool operation_id_matches(const operation_t *op);
bool operation_equal(const operation_t *a, const operation_t *b);
history_decision_t history_lookup(const history_t *h, const operation_t *op, const result_t **match);
bool history_accept(history_t *h, const operation_t *op, uint32_t seq, uint32_t applied_ms);
void history_complete(history_t *h);
