#include "inspection_app.h"
#include <string.h>

const char *b_action_name(b_action action) {
    static const char *names[] = {"CONFIGURE", "INSPECT", "QUERY", "CLOSE"};
    return names[(unsigned)action < 4 ? (unsigned)action : 0];
}
const char *b_stage_name(b_stage stage) {
    static const char *names[] = {"RECEIVED", "ACCEPTED", "COMPLETED", "REJECTED", "STATUS"};
    return names[(unsigned)stage < 5 ? (unsigned)stage : 0];
}
void b_app_init(b_app *app, const char *boot_id, b_publish_fn publish, void *context) {
    memset(app, 0, sizeof(*app));
    memcpy(app->boot_id, boot_id, B_BOOT_SIZE);
    app->publish = publish;
    app->context = context;
}
const b_record *b_app_find(const b_app *app, const char *id) {
    for (unsigned i = 0; i < app->job_count; ++i)
        if (!strcmp(app->jobs[i].request.id, id)) return &app->jobs[i];
    for (unsigned i = 0; i < app->command_count; ++i)
        if (!strcmp(app->commands[i].request.id, id)) return &app->commands[i];
    for (unsigned i = 0; i < app->query_count; ++i)
        if (!strcmp(app->queries[i].request.id, id)) return &app->queries[i];
    return NULL;
}
void b_app_view(const b_record *r, uint64_t now, b_view *view) {
    memset(view, 0, sizeof(*view));
    memcpy(view->id, r->request.id, B_ID_SIZE);
    memcpy(view->batch_id, r->request.batch_id, B_ID_SIZE);
    view->action = r->request.action;
    view->state = r->state;
    view->run_no = r->request.run_no;
    view->part_id = r->request.part_id;
    view->config_version = r->config_version;
    view->settings = r->frozen;
    view->error = r->error;
    view->fail = r->fail;
    if (r->state == B_ACCEPTED || r->state == B_COMPLETED)
        view->elapsed_ms = (r->state == B_COMPLETED ? r->completed_at : now) - r->started_at;
}
static void publish(b_app *app, b_record *r, b_stage stage) {
    unsigned bit = 1u << (unsigned)stage;
    if (stage == B_STATUS) {
        (void)app->publish(app, r, stage, app->context);
    } else if (app->publish(app, r, stage, app->context)) {
        r->pending &= ~bit;
    } else {
        r->pending |= bit;
    }
}
static void reject(b_app *app, b_record *r, const char *error) {
    r->error = error;
    r->state = B_REJECTED;
    publish(app, r, B_REJECTED);
}
static void accept(b_app *app, b_record *r, uint64_t now) {
    r->state = B_ACCEPTED;
    r->started_at = now;
    publish(app, r, B_ACCEPTED);
}
static void complete(b_app *app, b_record *r, uint64_t now) {
    /* Cache before publishing. Network loss/full TX never changes the result. */
    r->state = B_COMPLETED;
    r->completed_at = now;
    publish(app, r, B_COMPLETED);
}
static bool current_scope(const b_app *app, const b_request *req) {
    return app->run_open && req->run_no == app->run_no &&
           !strcmp(req->batch_id, app->batch_id);
}
static void service(b_app *app, b_record *r, uint64_t now) {
    const b_request *req = &r->request;
    if (!req->valid) { reject(app, r, "INVALID_REQUEST"); return; }
    if (strcmp(req->boot_id, app->boot_id)) { reject(app, r, "BOOT_MISMATCH"); return; }
    if (req->action == B_CONFIGURE) {
        if (app->active) { reject(app, r, "BUSY"); return; }
        if (app->config_version == UINT32_MAX) { reject(app, r, "VERSION_EXHAUSTED"); return; }
        bool new_run = !app->run_open && app->run_no < UINT32_MAX &&
                       req->run_no == app->run_no + 1;
        if (!new_run && !current_scope(app, req)) {
            reject(app, r, "STALE_SCOPE"); return;
        }
        app->run_open = true;
        app->run_no = req->run_no;
        memcpy(app->batch_id, req->batch_id, B_ID_SIZE);
        app->settings = req->settings;
        ++app->config_version;
        r->frozen = app->settings;
        r->config_version = app->config_version;
        accept(app, r, now);
        complete(app, r, now);
    } else if (req->action == B_INSPECT) {
        if (!current_scope(app, req)) { reject(app, r, "STALE_SCOPE"); return; }
        if (req->expected_config_version != app->config_version) {
            reject(app, r, "CONFIG_CHANGED"); return;
        }
        if (app->active) { reject(app, r, "BUSY"); return; }
        for (unsigned i = 0; i < app->job_count; ++i) {
            b_record *other = &app->jobs[i];
            if (other != r && other->request.part_id == req->part_id &&
                (other->state == B_ACCEPTED || other->state == B_COMPLETED)) {
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
    } else if (req->action == B_CLOSE) {
        if (!current_scope(app, req)) { reject(app, r, "STALE_SCOPE"); return; }
        if (app->active) { reject(app, r, "BUSY"); return; }
        r->config_version = app->config_version;
        r->frozen = app->settings;
        accept(app, r, now);
        app->run_open = false;
        complete(app, r, now);
    } else {
        /* QUERY's record is separate from its target; lookup never admits it. */
        const b_record *target = b_app_find(app, req->target_id);
        bool target_context = target && target != r && target->request.action != B_QUERY &&
                              target->request.run_no == req->run_no &&
                              !strcmp(target->request.batch_id, req->batch_id);
        if (!target_context && (req->run_no != app->run_no || strcmp(req->batch_id, app->batch_id))) {
            reject(app, r, "STALE_SCOPE"); return;
        }
        if (target_context) {
            r->target_found = true;
            b_app_view(target, now, &r->target);
        }
        accept(app, r, now);
        complete(app, r, now);
    }
}
bool b_app_request(b_app *app, const b_request *req, uint64_t now) {
    const b_record *old = b_app_find(app, req->id);
    if (old) {
        /* Conflict is a protocol error emitted by the frontend, never replaces
         * the original immutable operation record. */
        if (memcmp(old->request.fingerprint, req->fingerprint, 32)) return false;
        b_record *r = (b_record *)old;
        publish(app, r, r->state == B_ACCEPTED || r->state == B_RECEIVED ? B_STATUS : r->state);
        return true;
    }
    bool prospective = !strcmp(req->boot_id, app->boot_id) &&
                   req->action == B_CONFIGURE && !app->run_open &&
                   app->run_no < UINT32_MAX && req->run_no == app->run_no + 1;
    bool new_run = prospective && req->valid;
    if (new_run) {
        /* The explicit prior CLOSE invalidated all earlier run requests. */
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
    const b_record *target = req->action == B_QUERY ? b_app_find(app, req->target_id) : NULL;
    bool target_context = target && target->request.action != B_QUERY &&
                          target->request.run_no == req->run_no &&
                          !strcmp(target->request.batch_id, req->batch_id);
    /* Wrong boot/scope cannot consume the current run's retained history. */
    if (strcmp(req->boot_id, app->boot_id) ||
        (!prospective && !target_context &&
         (req->run_no != app->run_no || strcmp(req->batch_id, app->batch_id))) ||
        (req->action != B_QUERY && !prospective && !app->run_open))
        return false;
    b_record *r;
    if (req->action == B_QUERY) {
        if (req->query_no <= app->query_high_water) return false;
        r = &app->queries[app->query_next];
        if (r->pending) return false;
        app->query_high_water = req->query_no;
        app->query_next = (app->query_next + 1) % B_QUERIES;
        if (app->query_count < B_QUERIES) ++app->query_count;
    } else if (req->action == B_INSPECT) {
        if (app->job_count == B_JOBS) return false;
        r = &app->jobs[app->job_count++];
    } else {
        /* Leave the final command slot available for an idle CLOSE. */
        unsigned limit = req->action == B_CLOSE ? B_COMMANDS : B_COMMANDS - 1;
        if (app->command_count >= limit) return false;
        r = &app->commands[app->command_count++];
    }
    memset(r, 0, sizeof(*r));
    r->request = *req;
    r->state = B_RECEIVED; /* Queryable registration precedes RECEIVED. */
    publish(app, r, B_RECEIVED);
    service(app, r, now);
    return true;
}
static void flush(b_app *app, b_record *records, unsigned count) {
    /* Terminal outcomes take priority over intermediate unsent evidence. */
    static const b_stage order[] = {B_COMPLETED, B_REJECTED, B_RECEIVED, B_ACCEPTED};
    for (unsigned j = 0; j < 4; ++j)
        for (unsigned i = 0; i < count; ++i)
            if (records[i].pending & (1u << (unsigned)order[j]))
                publish(app, &records[i], order[j]);
}
void b_app_tick(b_app *app, uint64_t now) {
    if (app->active && now - app->active->started_at >= app->active->frozen.inspection_time_ms) {
        b_record *r = app->active;
        /* Signed 64-bit addition covers every approved uint32 part + int32 K.
         * Divisibility is independent of C/Python negative remainder signs. */
        int64_t value = (int64_t)r->request.part_id + r->frozen.k;
        r->fail = value % (int64_t)r->frozen.n == 0;
        app->active = NULL;
        complete(app, r, now);
    }
    flush(app, app->jobs, app->job_count);
    flush(app, app->commands, app->command_count);
    flush(app, app->queries, app->query_count);
}
