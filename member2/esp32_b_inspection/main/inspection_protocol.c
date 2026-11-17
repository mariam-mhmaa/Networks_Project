#include "inspection_protocol.h"
#include "vendor/cjson/cJSON.h"
#include <math.h>
#include <stdlib.h>
#include <string.h>
#ifdef _WIN32
#include <windows.h>
#include <bcrypt.h>
#else
#include "psa/crypto.h"
#endif

/* Strict flat JSON envelopes, bounded nesting and input, canonical SHA256
 * request fingerprints. Fingerprints detect conflicts; they are not auth. */
static bool hash(const char *bytes, size_t length, uint8_t out[32]) {
#ifdef _WIN32
    BCRYPT_ALG_HANDLE algorithm = NULL;
    BCRYPT_HASH_HANDLE digest = NULL;
    bool ok = BCryptOpenAlgorithmProvider(&algorithm, BCRYPT_SHA256_ALGORITHM, NULL, 0) == 0;
    if (ok) ok = BCryptCreateHash(algorithm, &digest, NULL, 0, NULL, 0, 0) == 0;
    if (ok) ok = BCryptHashData(digest, (PUCHAR)bytes, (ULONG)length, 0) == 0;
    if (ok) ok = BCryptFinishHash(digest, out, 32, 0) == 0;
    if (digest) BCryptDestroyHash(digest);
    if (algorithm) BCryptCloseAlgorithmProvider(algorithm, 0);
    return ok;
#else
    size_t written = 0;
    return psa_crypto_init() == PSA_SUCCESS &&
           psa_hash_compute(PSA_ALG_SHA_256, (const uint8_t *)bytes, length,
                            out, 32, &written) == PSA_SUCCESS && written == 32;
#endif
}
static bool utf8(const uint8_t *s, size_t n) {
    for (size_t i = 0; i < n;) {
        uint8_t c = s[i++];
        if (c < 0x80) { if (!c) return false; continue; }
        unsigned count;
        uint32_t value, minimum;
        if (c >= 0xc2 && c <= 0xdf) { count = 1; value = c & 31u; minimum = 0x80; }
        else if (c >= 0xe0 && c <= 0xef) { count = 2; value = c & 15u; minimum = 0x800; }
        else if (c >= 0xf0 && c <= 0xf4) { count = 3; value = c & 7u; minimum = 0x10000; }
        else return false;
        if (count > n - i) return false;
        for (unsigned j = 0; j < count; ++j) {
            uint8_t d = s[i++];
            if ((d & 0xc0) != 0x80) return false;
            value = (value << 6) | (d & 63u);
        }
        if (value < minimum || value > 0x10ffff || (value >= 0xd800 && value <= 0xdfff))
            return false;
    }
    return true;
}
static bool lexical(const uint8_t *s, size_t n) {
    if (!utf8(s, n)) return false;
    bool quoted = false;
    for (size_t i = 0; i < n; ++i) {
        uint8_t c = s[i];
        if (quoted) {
            if (c < 0x20) return false;
            if (c == '"') quoted = false;
            else if (c == '\\') {
                if (++i >= n) return false;
                if (s[i] == 'u' && i + 4 < n && !memcmp(s + i + 1, "0000", 4)) return false;
            }
        } else if (c == '"') quoted = true;
        else if ((c < 0x20 && c != 9 && c != 10 && c != 13) || c >= 0x80) return false;
        else if (c == '-' || (c >= '0' && c <= '9')) {
            size_t j = i;
            if (s[j] == '-' && ++j == n) return false;
            if (s[j] == '0') ++j;
            else {
                if (s[j] < '1' || s[j] > '9') return false;
                while (j < n && s[j] >= '0' && s[j] <= '9') ++j;
            }
            if (j < n && s[j] == '.') {
                ++j;
                if (j == n || s[j] < '0' || s[j] > '9') return false;
                while (j < n && s[j] >= '0' && s[j] <= '9') ++j;
            }
            if (j < n && (s[j] == 'e' || s[j] == 'E')) {
                ++j;
                if (j < n && (s[j] == '+' || s[j] == '-')) ++j;
                if (j == n || s[j] < '0' || s[j] > '9') return false;
                while (j < n && s[j] >= '0' && s[j] <= '9') ++j;
            }
            if (j < n && !strchr(" \t\r\n,}]", s[j])) return false;
            i = j - 1;
        }
    }
    return !quoted;
}
static const cJSON *get(const cJSON *root, const char *key) {
    return cJSON_GetObjectItemCaseSensitive(root, key);
}
static bool identifier(const cJSON *value, char *out, size_t capacity) {
    if (!cJSON_IsString(value)) return false;
    size_t n = strlen(value->valuestring);
    if (!n || n >= capacity) return false;
    for (size_t i = 0; i < n; ++i) {
        char c = value->valuestring[i];
        if (!((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') ||
              (c >= '0' && c <= '9') || strchr("_:-", c))) return false;
    }
    memcpy(out, value->valuestring, n + 1);
    return true;
}
static bool integer(const cJSON *root, const char *name, double low, double high, double *out) {
    const cJSON *value = get(root, name);
    if (!cJSON_IsNumber(value) || !isfinite(value->valuedouble) ||
        value->valuedouble < low || value->valuedouble > high ||
        floor(value->valuedouble) != value->valuedouble) return false;
    *out = value->valuedouble;
    return true;
}
static int compare_keys(const void *a, const void *b) {
    const cJSON *const *left = a, *const *right = b;
    return strcmp((*left)->string, (*right)->string);
}
/* Parse malformed/untrustworthy envelopes without inventing an ACK identity. */
static bool parse(const uint8_t *payload, size_t length, b_request *request) {
    if (!length || length > B_PAYLOAD_MAX || !lexical(payload, length)) return false;
    char bytes[B_PAYLOAD_MAX + 1];
    memcpy(bytes, payload, length); bytes[length] = 0;
    cJSON *root = cJSON_ParseWithLengthOpts(bytes, length + 1, NULL, true);
    if (!cJSON_IsObject(root)) { cJSON_Delete(root); return false; }
    cJSON *fields[16];
    unsigned count = 0;
    for (cJSON *item = root->child; item; item = item->next) {
        if (count == 16 || cJSON_IsObject(item) || cJSON_IsArray(item) ||
            (cJSON_IsNumber(item) && !isfinite(item->valuedouble))) {
            cJSON_Delete(root); return false;
        }
        fields[count++] = item;
    }
    qsort(fields, count, sizeof(fields[0]), compare_keys);
    for (unsigned i = 1; i < count; ++i)
        if (!strcmp(fields[i-1]->string, fields[i]->string)) { cJSON_Delete(root); return false; }
    memset(request, 0, sizeof(*request));
    const cJSON *type = get(root, "type");
    if (!cJSON_IsString(type)) { cJSON_Delete(root); return false; }
    bool found = false;
    for (unsigned i = 0; i < 4; ++i)
        if (!strcmp(type->valuestring, b_action_name((b_action)i))) {
            request->action = (b_action)i; found = true;
        }
    const char *id_key = request->action == B_INSPECT ? "job_id" : "cmd_id";
    double number;
    if (!found || !identifier(get(root, id_key), request->id, B_ID_SIZE) ||
        !identifier(get(root, "boot_id"), request->boot_id, B_BOOT_SIZE) ||
        !identifier(get(root, "batch_id"), request->batch_id, B_ID_SIZE) ||
        !integer(root, "run_no", 1, UINT32_MAX, &number)) {
        cJSON_Delete(root); return false;
    }
    request->run_no = (uint32_t)number;
    request->valid = integer(root, "v", 1, 1, &number);
    const char *allowed = request->action == B_CONFIGURE ?
        "|v|type|cmd_id|boot_id|batch_id|run_no|inspection_time_ms|N|K|" :
        request->action == B_INSPECT ?
        "|v|type|job_id|boot_id|batch_id|run_no|part_id|config_version|" :
        request->action == B_QUERY ?
        "|v|type|cmd_id|boot_id|batch_id|run_no|target_id|query_no|" :
        "|v|type|cmd_id|boot_id|batch_id|run_no|";
    for (unsigned i = 0; i < count; ++i) {
        char key[80];
        size_t n = strlen(fields[i]->string);
        if (n > 76) { request->valid = false; continue; }
        key[0] = '|'; memcpy(key + 1, fields[i]->string, n);
        key[n+1] = '|'; key[n+2] = 0;
        if (!strstr(allowed, key)) request->valid = false;
    }
    if (request->action == B_CONFIGURE) {
        bool ok = integer(root, "inspection_time_ms", 1, 600000, &number);
        if (ok) request->settings.inspection_time_ms = (uint32_t)number;
        request->valid &= ok;
        ok = integer(root, "N", 1, INT32_MAX, &number);
        if (ok) request->settings.n = (uint32_t)number;
        request->valid &= ok;
        ok = integer(root, "K", INT32_MIN, INT32_MAX, &number);
        if (ok) request->settings.k = (int32_t)number;
        request->valid &= ok;
    } else if (request->action == B_INSPECT) {
        bool ok = integer(root, "part_id", 1, UINT32_MAX, &number);
        if (ok) request->part_id = (uint32_t)number;
        request->valid &= ok;
        ok = integer(root, "config_version", 1, UINT32_MAX, &number);
        if (ok) request->expected_config_version = (uint32_t)number;
        request->valid &= ok;
    } else if (request->action == B_QUERY) {
        request->valid &= identifier(get(root, "target_id"), request->target_id, B_ID_SIZE);
        bool ok = integer(root, "query_no", 1, UINT32_MAX, &number);
        if (ok) request->query_no = (uint32_t)number;
        request->valid &= ok;
    }
    cJSON *canonical = cJSON_CreateObject();
    bool ok = canonical != NULL;
    for (unsigned i = 0; ok && i < count; ++i) {
        cJSON *copy = cJSON_Duplicate(fields[i], false);
        ok = copy && cJSON_AddItemToObject(canonical, fields[i]->string, copy);
        if (!ok) cJSON_Delete(copy);
    }
    char *encoded = ok ? cJSON_PrintUnformatted(canonical) : NULL;
    ok = encoded && hash(encoded, strlen(encoded), request->fingerprint);
    cJSON_free(encoded);
    cJSON_Delete(canonical); cJSON_Delete(root);
    return ok;
}
static void number(cJSON *root, const char *key, double value) { cJSON_AddNumberToObject(root, key, value); }
static void string(cJSON *root, const char *key, const char *value) { cJSON_AddStringToObject(root, key, value); }
static cJSON *settings(b_settings values) {
    cJSON *root = cJSON_CreateObject();
    if (!root) return NULL;
    number(root, "inspection_time_ms", values.inspection_time_ms);
    number(root, "N", values.n); number(root, "K", values.k);
    return root;
}
static cJSON *view(const b_view *value) {
    cJSON *root = cJSON_CreateObject();
    if (!root) return NULL;
    string(root, value->action == B_INSPECT ? "job_id" : "cmd_id", value->id);
    string(root, "action", b_action_name(value->action));
    string(root, "batch_id", value->batch_id); number(root, "run_no", value->run_no);
    string(root, "state", value->state == B_ACCEPTED ? "IN_PROGRESS" : b_stage_name(value->state));
    if (value->error) string(root, "error", value->error);
    if (value->action == B_INSPECT) number(root, "part_id", value->part_id);
    number(root, "config_version", value->config_version);
    cJSON_AddItemToObject(root, "settings", settings(value->settings));
    number(root, "elapsed_ms", (double)value->elapsed_ms);
    if (value->action == B_INSPECT && value->state == B_COMPLETED)
        string(root, "verdict", value->fail ? "FAIL" : "PASS");
    if (value->action == B_CLOSE && value->state == B_COMPLETED)
        cJSON_AddBoolToObject(root, "closed", true);
    return root;
}
static bool send_json(b_protocol *protocol, cJSON *root) {
    if (!root) return false;
    char bytes[B_PAYLOAD_MAX + 1];
    bool ok = cJSON_PrintPreallocated(root, bytes, sizeof(bytes), false) &&
              b_tcp_queue(protocol->transport, (const uint8_t *)bytes, strlen(bytes));
    cJSON_Delete(root);
    return ok;
}
static bool publish(const b_app *app, const b_record *record, b_stage stage, void *context) {
    b_protocol *p = context;
    if (p->transport->client == B_INVALID_SOCKET || p->transport->count == B_TX_SLOTS) return false;
    cJSON *root = cJSON_CreateObject();
    if (!root) return false;
    number(root, "v", 1); string(root, "type", b_stage_name(stage));
    string(root, "boot_id", app->boot_id);
    string(root, "action", b_action_name(record->request.action));
    string(root, record->request.action == B_INSPECT ? "job_id" : "cmd_id", record->request.id);
    string(root, "batch_id", record->request.batch_id); number(root, "run_no", record->request.run_no);
    if (record->request.action == B_INSPECT) number(root, "part_id", record->request.part_id);
    if (stage == B_REJECTED) string(root, "error", record->error);
    if (stage == B_STATUS) {
        string(root, "state", record->state == B_ACCEPTED ? "IN_PROGRESS" : "PENDING_VALIDATION");
    } else if (stage == B_COMPLETED) {
        if (record->request.action == B_QUERY) {
            string(root, "target_id", record->request.target_id);
            number(root, "query_no", record->request.query_no);
            if (record->target_found) cJSON_AddItemToObject(root, "target", view(&record->target));
            else cJSON_AddNullToObject(root, "target");
        } else {
            b_view snapshot;
            b_app_view(record, p->now_ms, &snapshot);
            cJSON_AddItemToObject(root, "result", view(&snapshot));
        }
    }
    return send_json(p, root);
}
void b_protocol_init(b_protocol *p, b_tcp_service *transport, const char *boot) {
    memset(p, 0, sizeof(*p)); p->transport = transport;
    b_app_init(&p->app, boot, publish, p);
}
bool b_protocol_receive(const uint8_t *bytes, size_t length, void *context) {
    b_protocol *p = context;
    b_request request;
    if (!parse(bytes, length, &request)) return false;
    if (b_app_request(&p->app, &request, p->now_ms)) return true;
    cJSON *error = cJSON_CreateObject();
    if (!error) return false;
    number(error, "v", 1); string(error, "type", "ERROR");
    string(error, "boot_id", p->app.boot_id);
    string(error, "action", b_action_name(request.action));
    string(error, request.action == B_INSPECT ? "job_id" : "cmd_id", request.id);
    string(error, "batch_id", request.batch_id); number(error, "run_no", request.run_no);
    if (request.action == B_INSPECT) number(error, "part_id", request.part_id);
    const b_record *old = b_app_find(&p->app, request.id);
    string(error, "error", old ? "ID_CONFLICT" :
           strcmp(request.boot_id, p->app.boot_id) ? "BOOT_MISMATCH" :
           request.action == B_QUERY && request.query_no <= p->app.query_high_water ? "STALE_QUERY" :
           request.run_no != p->app.run_no || !p->app.run_open ? "STALE_SCOPE" : "HISTORY_FULL");
    return send_json(p, error);
}
void b_protocol_tick(b_protocol *p, uint64_t now) {
    p->now_ms = now;
    b_app_tick(&p->app, now);
    bool connected = p->transport->client != B_INVALID_SOCKET;
    if (connected && p->generation != p->transport->generation) {
        p->generation = p->transport->generation; p->next_heartbeat = 0;
    }
    if (!connected || now < p->next_heartbeat || p->transport->count) return;
    cJSON *root = cJSON_CreateObject();
    if (!root) return;
    number(root, "v", 1); string(root, "type", "HEARTBEAT");
    string(root, "boot_id", p->app.boot_id);
    number(root, "run_no", p->app.run_no); string(root, "batch_id", p->app.batch_id);
    cJSON_AddBoolToObject(root, "run_open", p->app.run_open);
    string(root, "state", p->app.active ? "BUSY" : "IDLE");
    number(root, "config_version", p->app.config_version);
    number(root, "query_high_water", p->app.query_high_water);
    number(root, "jobs_retained", p->app.job_count);
    number(root, "commands_retained", p->app.command_count);
    number(root, "executions", (double)p->app.executions);
    if (send_json(p, root)) p->next_heartbeat = now + 500;
}
