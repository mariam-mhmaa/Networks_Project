#include "station_app.h"
#include <string.h>

const char *s_action_name(s_action action) {
    static const char *names[] = {"CONFIGURE", "INSPECT", "QUERY", "CLOSE", "RETIRE"};
    return names[(unsigned)action < 5 ? (unsigned)action : 0];
}
const char *s_stage_name(s_stage stage) {
    static const char *names[] = {"RECEIVED", "ACCEPTED", "COMPLETED", "REJECTED", "STATUS"};
    return names[(unsigned)stage < 5 ? (unsigned)stage : 0];
}
void s_app_init(s_app *app, const char *boot_id, bool production, s_publish_fn publish, void *context) {
    memset(app, 0, sizeof(*app));
    memcpy(app->boot_id, boot_id, S_BOOT_SIZE);
    app->production = production;
    app->publish = publish;
    app->context = context;
}
const s_record *s_app_find(const s_app *app, const char *id) {
    for (unsigned i = 0; i < app->job_count; ++i)
        if (!strcmp(app->jobs[i].request.id, id)) return &app->jobs[i];
    for (unsigned i = 0; i < app->command_count; ++i)
        if (!strcmp(app->commands[i].request.id, id)) return &app->commands[i];
    for (unsigned i = 0; i < app->query_count; ++i)
        if (!strcmp(app->queries[i].request.id, id)) return &app->queries[i];
    for (unsigned i = 0; i < app->retirement_count; ++i)
        if (!strcmp(app->retirements[i].request.id, id)) return &app->retirements[i];
    return NULL;
}
void s_app_view(const s_record *r, uint64_t now, s_view *view) {
    memset(view, 0, sizeof(*view));
    memcpy(view->id, r->request.id, S_ID_SIZE);
    memcpy(view->batch_id, r->request.batch_id, S_ID_SIZE);
    view->action = r->request.action;
    view->state = r->state;
    view->run_no = r->request.run_no;
    view->part_id = r->request.part_id;
    view->config_version = r->config_version;
    view->settings = r->frozen;
    view->error = r->error;
    view->fail = r->fail;
    view->retired = r->target_found && r->request.action == S_JOB;
    if (r->state == S_ACCEPTED || r->state == S_COMPLETED)
        view->elapsed_ms = (r->state == S_COMPLETED ? r->completed_at : now) - r->started_at;
}
static void publish(s_app *app, s_record *r, s_stage stage) {
    unsigned bit = 1u << (unsigned)stage;
    if (stage == S_STATUS) {
        (void)app->publish(app, r, stage, app->context);
    } else if (app->publish(app, r, stage, app->context)) {
        r->pending &= ~bit;
    } else {
        r->pending |= bit;
    }
}
static void reject(s_app *app, s_record *r, const char *error) {
    r->error = error;
    r->state = S_REJECTED;
    publish(app, r, S_REJECTED);
}
static void accept(s_app *app, s_record *r, uint64_t now) {
    r->state = S_ACCEPTED;
    r->started_at = now;
    publish(app, r, S_ACCEPTED);
}
static void complete(s_app *app, s_record *r, uint64_t now) {
    /* Cache before publishing. Network loss/full TX never changes the result. */
    r->state = S_COMPLETED;
    r->completed_at = now;
    publish(app, r, S_COMPLETED);
}
static bool current_scope(const s_app *app, const s_request *req) {
    return app->run_open && req->run_no == app->run_no &&
           !strcmp(req->batch_id, app->batch_id);
}
static void service(s_app *app, s_record *r, uint64_t now) {
    const s_request *req = &r->request;
    if (!req->valid) { reject(app, r, "INVALID_REQUEST"); return; }
    if (strcmp(req->boot_id, app->boot_id)) { reject(app, r, "BOOT_MISMATCH"); return; }
    if (req->action == S_CONFIGURE) {
        if (app->active) { reject(app, r, "BUSY"); return; }
        if (app->config_version == UINT32_MAX) { reject(app, r, "VERSION_EXHAUSTED"); return; }
        bool new_run = !app->run_open && app->run_no < UINT32_MAX &&
                       req->run_no == app->run_no + 1;
        if (!new_run && !current_scope(app, req)) {
            reject(app, r, "STALE_SCOPE"); return;
        }
        app->run_open = true;
        app->run_no = req->run_no;
        memcpy(app->batch_id, req->batch_id, S_ID_SIZE);
        app->settings = req->settings;
        ++app->config_version;
        r->frozen = app->settings;
        r->config_version = app->config_version;
        accept(app, r, now);
        complete(app, r, now);
    } else if (req->action == S_JOB) {
        if (!current_scope(app, req)) { reject(app, r, "STALE_SCOPE"); return; }
        if (req->expected_config_version != app->config_version) {
            reject(app, r, "CONFIG_CHANGED"); return;
        }
        if (app->active) { reject(app, r, "BUSY"); return; }
        for (unsigned i = 0; i < app->job_count; ++i) {
            s_record *other = &app->jobs[i];
            if (other != r && other->request.part_id == req->part_id &&
                (other->state == S_ACCEPTED || other->state == S_COMPLETED || other->part_fenced)) {
                reject(app, r, "PART_ALREADY_ACCEPTED"); return;
            }
        }
        r->frozen = app->settings;
        r->config_version = app->config_version;
        /* Commit execution ownership BEFORE publishing acceptance. */
        r->started_at = now;
        app->active = r;
        ++app->executions;
        accept(app, r, now);
    } else if (req->action == S_RETIRE) {
        if (!current_scope(app, req)) { reject(app, r, "STALE_SCOPE"); return; }
        const s_record *target = s_app_find(app, req->target_id);
        if (target && (target->request.action != S_JOB ||
            target->request.part_id != req->part_id ||
            target->request.run_no != req->run_no || strcmp(target->request.batch_id, req->batch_id))) {
            reject(app, r, "TARGET_CONFLICT"); return;
        }
        if (target && (target->state == S_ACCEPTED || target->state == S_RECEIVED)) {
            reject(app, r, "BUSY"); return;
        }
        if (!target) {
            for (unsigned i = 0; i < app->job_count; ++i)
                if (app->jobs[i].request.part_id == req->part_id) {
                    reject(app, r, "TARGET_CONFLICT"); return;
                }
            if (app->job_count == S_JOBS) { reject(app, r, "HISTORY_FULL"); return; }
            s_record *fence = &app->jobs[app->job_count++];
            memset(fence, 0, sizeof(*fence));
            fence->request = *req;
            memcpy(fence->request.id, req->target_id, S_ID_SIZE);
            fence->request.action = S_JOB;
            fence->state = S_REJECTED;
            fence->error = "RETIRED";
            fence->target_found = true; /* retained part fence, not execution */
            target = fence;
        }
        ((s_record *)target)->part_fenced = true;
        r->target_found = true;
        s_app_view(target, now, &r->target);
        r->frozen = app->settings;
        r->config_version = app->config_version;
        accept(app, r, now);
        complete(app, r, now);
    } else if (req->action == S_CLOSE) {
        if (!current_scope(app, req)) { reject(app, r, "STALE_SCOPE"); return; }
        if (app->active) { reject(app, r, "BUSY"); return; }
        r->config_version = app->config_version;
        r->frozen = app->settings;
        accept(app, r, now);
        app->run_open = false;
        complete(app, r, now);
    } else {
        /* QUERY's record is separate from its target; lookup never admits it. */
        const s_record *target = s_app_find(app, req->target_id);
        bool target_context = target && target != r && target->request.action != S_QUERY &&
                              target->request.run_no == req->run_no &&
                              !strcmp(target->request.batch_id, req->batch_id);
        if (!target_context && (req->run_no != app->run_no || strcmp(req->batch_id, app->batch_id))) {
            reject(app, r, "STALE_SCOPE"); return;
        }
        if (target_context) {
            r->target_found = true;
            s_app_view(target, now, &r->target);
        }
        accept(app, r, now);
        complete(app, r, now);
    }
}
bool s_app_request(s_app *app, const s_request *req, uint64_t now) {
    const s_record *old = s_app_find(app, req->id);
    if (old) {
        /* Conflict is a protocol error emitted by the frontend, never replaces
         * the original immutable operation record. */
        if (old->request.action == S_JOB && old->target_found) {
            if (req->action != S_JOB || req->part_id != old->request.part_id ||
                req->run_no != old->request.run_no || strcmp(req->batch_id, old->request.batch_id) ||
                strcmp(req->boot_id, old->request.boot_id)) return false;
        } else if (memcmp(old->request.fingerprint, req->fingerprint, 32)) return false;
        s_record *r = (s_record *)old;
        publish(app, r, r->state == S_ACCEPTED || r->state == S_RECEIVED ? S_STATUS : r->state);
        return true;
    }
    bool prospective = !strcmp(req->boot_id, app->boot_id) &&
                   req->action == S_CONFIGURE && !app->run_open &&
                   app->run_no < UINT32_MAX && req->run_no == app->run_no + 1;
    bool new_run = prospective && req->valid;
    if (new_run) {
        /* The explicit prior CLOSE invalidated all earlier run requests. */
        app->retirement_count = 0;
        memset(app->retirements, 0, sizeof(app->retirements));
        app->job_count = 0;
        memset(app->jobs, 0, sizeof(app->jobs));
        /* Retain any rejected first-configuration requests for this new run.
         * Opening a valid run must not make those IDs reusable. */
        unsigned kept = 0;
        for (unsigned i = 0; i < app->command_count; ++i)
            if (app->commands[i].request.run_no == req->run_no) {
                if (kept != i) app->commands[kept] = app->commands[i];
                ++kept;
            }
        app->command_count = kept;
        app->query_count = app->query_next = 0;
        memset(app->queries, 0, sizeof(app->queries));
    }
    const s_record *target = req->action == S_QUERY ? s_app_find(app, req->target_id) : NULL;
    bool target_context = target && target->request.action != S_QUERY &&
                          target->request.run_no == req->run_no &&
                          !strcmp(target->request.batch_id, req->batch_id);
    /* Wrong boot/scope cannot consume the current run's retained history. */
    if (strcmp(req->boot_id, app->boot_id) ||
        (!prospective && !target_context &&
         (req->run_no != app->run_no || strcmp(req->batch_id, app->batch_id))) ||
        (req->action != S_QUERY && !prospective && !app->run_open))
        return false;
    s_record *r;
    if (req->action == S_QUERY) {
        if (req->query_no <= app->query_high_water) return false;
        r = &app->queries[app->query_next];
        if (r->pending) return false;
        app->query_high_water = req->query_no;
        app->query_next = (app->query_next + 1) % S_QUERIES;
        if (app->query_count < S_QUERIES) ++app->query_count;
    } else if (req->action == S_RETIRE) {
        if (app->retirement_count == S_JOBS) return false;
        r = &app->retirements[app->retirement_count++];
    } else if (req->action == S_JOB) {
        if (app->job_count == S_JOBS) return false;
        r = &app->jobs[app->job_count++];
    } else {
        /* Leave the final command slot available for an idle CLOSE. */
        unsigned limit = req->action == S_CLOSE ? S_COMMANDS : S_COMMANDS - 1;
        if (app->command_count >= limit) return false;
        r = &app->commands[app->command_count++];
    }
    memset(r, 0, sizeof(*r));
    r->request = *req;
    r->state = S_RECEIVED; /* Queryable registration precedes RECEIVED. */
    publish(app, r, S_RECEIVED);
    service(app, r, now);
    return true;
}
static void flush(s_app *app, s_record *records, unsigned count) {
    /* Terminal outcomes take priority over intermediate unsent evidence. */
    static const s_stage order[] = {S_COMPLETED, S_REJECTED, S_RECEIVED, S_ACCEPTED};
    for (unsigned j = 0; j < 4; ++j)
        for (unsigned i = 0; i < count; ++i)
            if (records[i].pending & (1u << (unsigned)order[j]))
                publish(app, &records[i], order[j]);
}
void s_app_tick(s_app *app, uint64_t now) {
    if (app->active && now - app->active->started_at >= app->active->frozen.duration_ms) {
        s_record *r = app->active;
        /* Signed 64-bit addition covers every approved uint32 part + int32 K.
         * Divisibility is independent of C/Python negative remainder signs. */
        int64_t value = (int64_t)r->request.part_id + r->frozen.k;
        r->fail = !app->production && r->frozen.n && value % (int64_t)r->frozen.n == 0;
        app->active = NULL;
        complete(app, r, now);
    }
    flush(app, app->jobs, app->job_count);
    flush(app, app->commands, app->command_count);
    flush(app, app->queries, app->query_count);
    flush(app, app->retirements, app->retirement_count);
}
