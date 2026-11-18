#pragma once
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define S_ID_SIZE 97
#define S_BOOT_SIZE 33
#define S_JOBS 64
#define S_COMMANDS 16
#define S_QUERIES 8

typedef enum { S_CONFIGURE, S_JOB, S_QUERY, S_CLOSE, S_RETIRE } s_action;
typedef enum { S_RECEIVED, S_ACCEPTED, S_COMPLETED, S_REJECTED, S_STATUS } s_stage;
typedef struct { uint32_t duration_ms, n; int32_t k; } s_settings;
typedef struct {
    char id[S_ID_SIZE], batch_id[S_ID_SIZE], boot_id[S_BOOT_SIZE], target_id[S_ID_SIZE];
    uint8_t fingerprint[32];
    s_action action;
    uint32_t run_no, part_id, query_no, expected_config_version, transport_seq;
    s_settings settings;
    bool valid;
} s_request;
typedef struct {
    char id[S_ID_SIZE], batch_id[S_ID_SIZE];
    s_action action;
    s_stage state;
    uint32_t run_no, part_id, config_version;
    s_settings settings;
    uint64_t elapsed_ms;
    const char *error;
    bool fail, retired;
} s_view;
typedef struct {
    s_request request;
    s_stage state;
    const char *error;
    uint64_t started_at, completed_at;
    s_settings frozen;
    uint32_t config_version;
    unsigned pending;
    bool fail, target_found, part_fenced;
    s_view target;
} s_record;
struct s_app;
/* Returning false means initial transmission could not be queued. The outcome
 * remains in history; no execution or timer ever waits for this callback. */
typedef bool (*s_publish_fn)(const struct s_app *, const s_record *, s_stage, void *);
typedef struct s_app {
    char boot_id[S_BOOT_SIZE], batch_id[S_ID_SIZE];
    uint32_t run_no, config_version, query_high_water;
    bool run_open, production;
    s_settings settings;
    s_record jobs[S_JOBS], commands[S_COMMANDS], queries[S_QUERIES], retirements[S_JOBS];
    unsigned job_count, command_count, query_count, query_next, retirement_count;
    s_record *active;
    uint64_t executions;
    s_publish_fn publish;
    void *context;
} s_app;

void s_app_init(s_app *, const char *boot_id, bool production, s_publish_fn, void *);
/* False: admission could not reserve a record. Never executes unregistered work. */
bool s_app_request(s_app *, const s_request *, uint64_t now_ms);
void s_app_tick(s_app *, uint64_t now_ms);
const s_record *s_app_find(const s_app *, const char *id);
void s_app_view(const s_record *, uint64_t now_ms, s_view *);
const char *s_action_name(s_action);
const char *s_stage_name(s_stage);
