#pragma once
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define B_ID_SIZE 97
#define B_BOOT_SIZE 33
#define B_JOBS 64
#define B_COMMANDS 16
#define B_QUERIES 8

typedef enum { B_CONFIGURE, B_INSPECT, B_QUERY, B_CLOSE } b_action;
typedef enum { B_RECEIVED, B_ACCEPTED, B_COMPLETED, B_REJECTED, B_STATUS } b_stage;
typedef struct { uint32_t inspection_time_ms, n; int32_t k; } b_settings;
typedef struct {
    char id[B_ID_SIZE], batch_id[B_ID_SIZE], boot_id[B_BOOT_SIZE], target_id[B_ID_SIZE];
    uint8_t fingerprint[32];
    b_action action;
    uint32_t run_no, part_id, query_no, expected_config_version;
    b_settings settings;
    bool valid;
} b_request;
typedef struct {
    char id[B_ID_SIZE], batch_id[B_ID_SIZE];
    b_action action;
    b_stage state;
    uint32_t run_no, part_id, config_version;
    b_settings settings;
    uint64_t elapsed_ms;
    const char *error;
    bool fail;
} b_view;
typedef struct {
    b_request request;
    b_stage state;
    const char *error;
    uint64_t started_at, completed_at;
    b_settings frozen;
    uint32_t config_version;
    unsigned pending;
    bool fail, target_found;
    b_view target;
} b_record;
struct b_app;
/* Returning false means initial transmission could not be queued. The outcome
 * remains in history; no execution or timer ever waits for this callback. */
typedef bool (*b_publish_fn)(const struct b_app *, const b_record *, b_stage, void *);
typedef struct b_app {
    char boot_id[B_BOOT_SIZE], batch_id[B_ID_SIZE];
    uint32_t run_no, config_version, query_high_water;
    bool run_open;
    b_settings settings;
    b_record jobs[B_JOBS], commands[B_COMMANDS], queries[B_QUERIES];
    unsigned job_count, command_count, query_count, query_next;
    b_record *active;
    uint64_t executions;
    b_publish_fn publish;
    void *context;
} b_app;

void b_app_init(b_app *, const char *boot_id, b_publish_fn, void *);
/* False: admission could not reserve a record. Never executes unregistered work. */
bool b_app_request(b_app *, const b_request *, uint64_t now_ms);
void b_app_tick(b_app *, uint64_t now_ms);
const b_record *b_app_find(const b_app *, const char *id);
void b_app_view(const b_record *, uint64_t now_ms, b_view *);
const char *b_action_name(b_action);
const char *b_stage_name(b_stage);
