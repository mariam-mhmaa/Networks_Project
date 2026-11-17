#include <string.h>

#include "esp_event.h"
#include "esp_log.h"
#include "esp_netif.h"
#include "esp_wifi.h"
#include "esp_random.h"
#include "esp_timer.h"
#include "nvs_flash.h"
#include "freertos/FreeRTOS.h"
#include "freertos/event_groups.h"
#include "freertos/task.h"
#include "lwip/sockets.h"
#include "tcp_service.h"
#include "inspection_protocol.h"

static const char *TAG = "inspection_wifi";
static EventGroupHandle_t network_events;
#define WIFI_READY BIT0

static bool receive_frame(const uint8_t *payload, size_t length, void *context)
{
#ifdef CONFIG_INSPECTION_TRANSPORT_DIAGNOSTIC
    /* Hardware transport test only; this is never an application ACK. */
    return b_tcp_queue((b_tcp_service *)context, payload, length);
#else
    return b_protocol_receive(payload, length, context);
#endif
}

static void tcp_task(void *context)
{
    (void)context;
    static b_tcp_service service;
#ifdef CONFIG_INSPECTION_TRANSPORT_DIAGNOSTIC
    b_tcp_init(&service, receive_frame, &service);
    ESP_LOGW(TAG, "TRANSPORT DIAGNOSTIC: echo enabled; no inspection/application protocol");
#else
    static b_protocol protocol;
    uint8_t random[16];
    char boot[B_BOOT_SIZE];
    esp_fill_random(random, sizeof(random));
    static const char hex[] = "0123456789abcdef";
    for (unsigned i = 0; i < 16; ++i) {
        boot[i*2] = hex[random[i] >> 4]; boot[i*2+1] = hex[random[i] & 15u];
    }
    boot[32] = 0;
    b_tcp_init(&service, receive_frame, &protocol);
    b_protocol_init(&protocol, &service, boot);
    ESP_LOGI(TAG, "Inspection protocol v1 boot=%s", boot);
#endif
    uint64_t next_listener_attempt = 0;
    for (;;) {
        uint64_t now_ms = (uint64_t)(esp_timer_get_time() / 1000);
#ifndef CONFIG_INSPECTION_TRANSPORT_DIAGNOSTIC
        /* Accepted work progresses even while Wi-Fi/TCP is unavailable. */
        b_protocol_tick(&protocol, now_ms);
#endif
        if (!(xEventGroupGetBits(network_events) & WIFI_READY)) {
            b_tcp_close(&service);
            vTaskDelay(pdMS_TO_TICKS(20));
            continue;
        }
        if (service.listener == B_INVALID_SOCKET) {
            if (now_ms < next_listener_attempt ||
                !b_tcp_open(&service, htonl(INADDR_ANY), CONFIG_INSPECTION_TCP_PORT)) {
                if (now_ms >= next_listener_attempt) {
                    ESP_LOGW(TAG, "TCP listener unavailable; retrying transport only");
                    next_listener_attempt = now_ms + 1000;
                }
                vTaskDelay(pdMS_TO_TICKS(20));
                continue;
            }
        }
        b_tcp_poll(&service);
        vTaskDelay(pdMS_TO_TICKS(20));
    }
}

static void wifi_event_handler(void *arg, esp_event_base_t event_base,
                               int32_t event_id, void *event_data)
{
    if (event_base == WIFI_EVENT && event_id == WIFI_EVENT_STA_START) {
        ESP_LOGI(TAG, "Wi-Fi started; connecting to hotspot");
        ESP_ERROR_CHECK(esp_wifi_connect());
    } else if (event_base == WIFI_EVENT && event_id == WIFI_EVENT_STA_DISCONNECTED) {
        xEventGroupClearBits(network_events, WIFI_READY);
        const wifi_event_sta_disconnected_t *event = event_data;
        ESP_LOGW(TAG, "Wi-Fi disconnected (reason %u); reconnecting", event->reason);
        ESP_ERROR_CHECK(esp_wifi_connect());
    } else if (event_base == IP_EVENT && event_id == IP_EVENT_STA_GOT_IP) {
        xEventGroupSetBits(network_events, WIFI_READY);
        const ip_event_got_ip_t *event = event_data;
        ESP_LOGI(TAG, "Wi-Fi connected; IPv4 address: " IPSTR,
                 IP2STR(&event->ip_info.ip));
    }
}

void app_main(void)
{
    network_events = xEventGroupCreate();
    if (network_events == NULL) {
        ESP_LOGE(TAG, "Cannot allocate network event group");
        return;
    }
    if (strlen(CONFIG_INSPECTION_WIFI_SSID) == 0 ||
        strlen(CONFIG_INSPECTION_WIFI_PASSWORD) < 8) {
        ESP_LOGE(TAG, "Set the hotspot name and a WPA2 password (at least 8 characters) in project configuration");
        return;
    }

    esp_err_t err = nvs_flash_init();
    if (err == ESP_ERR_NVS_NO_FREE_PAGES || err == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_ERROR_CHECK(nvs_flash_erase());
        err = nvs_flash_init();
    }
    ESP_ERROR_CHECK(err);

    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());
    esp_netif_create_default_wifi_sta();

    const wifi_init_config_t wifi_init = WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&wifi_init));
    ESP_ERROR_CHECK(esp_event_handler_register(WIFI_EVENT, ESP_EVENT_ANY_ID,
                                               wifi_event_handler, NULL));
    ESP_ERROR_CHECK(esp_event_handler_register(IP_EVENT, IP_EVENT_STA_GOT_IP,
                                               wifi_event_handler, NULL));

    wifi_config_t wifi_config = {
        .sta = {
            .ssid = CONFIG_INSPECTION_WIFI_SSID,
            .password = CONFIG_INSPECTION_WIFI_PASSWORD,
            .threshold.authmode = WIFI_AUTH_WPA2_PSK,
        },
    };

    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_STA));
    ESP_ERROR_CHECK(esp_wifi_set_config(WIFI_IF_STA, &wifi_config));
    ESP_ERROR_CHECK(esp_wifi_start());
    if (xTaskCreate(tcp_task, "inspection_tcp", 8192, NULL, 5, NULL) != pdPASS) {
        ESP_LOGE(TAG, "Cannot start TCP service task");
    }
}
